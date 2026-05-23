from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
import re
import time
from typing import Any

from verbatim.analytics.latency import summarize_call_events
from verbatim.events import EventLogger, new_id


SECRET_TEXT_RE = re.compile(
    r"(wss://[^\s\"']+|https?://[^\s\"']*(?:token|jwt|join)[^\s\"']*|"
    r"(?:sk-|xai-|gsk_)[A-Za-z0-9_-]+)",
    re.IGNORECASE,
)


def _safe_metadata_text(value: Any) -> str:
    return SECRET_TEXT_RE.sub("[redacted]", str(value))


def _frame_text(frame: Any) -> str | None:
    for attr in ("text", "transcript", "content"):
        value = getattr(frame, attr, None)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _frame_metadata(frame: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {"frame_type": frame.__class__.__name__}
    for attr in (
        "language",
        "user_id",
        "participant_id",
        "request_id",
        "processor",
        "fatal",
        "error",
        "final",
        "is_final",
        "finalized",
        "speech_final",
        "confidence",
        "start",
        "duration",
        "stop_secs",
    ):
        value = getattr(frame, attr, None)
        if value is not None:
            metadata[attr] = _safe_metadata_text(value)
    result = getattr(frame, "result", None)
    if isinstance(result, dict):
        for key in (
            "event",
            "type",
            "is_final",
            "speech_final",
            "from_finalize",
            "duration",
            "start",
            "channel_index",
        ):
            value = result.get(key)
            if value is not None:
                metadata[f"result_{key}"] = str(value)
    text = _frame_text(frame)
    if text:
        metadata["text_preview"] = text[:240]
    return metadata


WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)?")


class CallRecorder:
    """Stateful call instrumentation shared by Pipecat processors and event handlers."""

    def __init__(self, logger: EventLogger) -> None:
        self.logger = logger
        self.events: list[dict[str, Any]] = []
        self.current_turn_id: str | None = None
        self.turn_index = 0
        self._seen_by_turn: set[tuple[str, str]] = set()
        self._assistant_chunks: dict[str, list[str]] = {}
        self._assistant_final_transcripts: dict[str, str] = {}
        self._user_transcripts: dict[str, str] = {}
        self._assistant_speaking = False
        self._last_assistant_audio_ms: float | None = None
        self._llm_active_turn_id: str | None = None
        self._llm_start_reason_by_turn: dict[str, str] = {}
        self._cancelled_llm_turn_ids: set[str] = set()
        self._pending_pipeline_interrupts: deque[str] = deque()
        self._last_completed_turn_id: str | None = None
        self._phantom_prevented_frame_ids: set[int] = set()
        self._drop_frame_ids: set[int] = set()
        self._seen_frame_ids: set[int] = set()
        self._seen_frame_id_order: deque[int] = deque(maxlen=512)
        self._candidate_user_speech_started_ms: float | None = None
        self._candidate_user_turn_id: str | None = None
        self._assistant_playback_started_ms_by_turn: dict[str, float] = {}
        self._last_user_commit_turn_id: str | None = None
        self._last_user_commit_text: str | None = None
        self._last_user_commit_ms: float | None = None
        self.llm_provider = "gemini"
        self.llm_model = "gemini-2.5-flash"
        self.assistant_min_speak_ms_before_barge_in = 400
        self.barge_in_min_speech_ms = 300
        self.barge_in_min_transcript_words = 2
        self.mute_user_while_bot_speaking = False
        self.hard_interrupt_phrases = ("stop", "wait", "hold on", "let me finish", "actually", "no")
        self.utterance_split_window_ms = 1200
        self.user_resume_after_assistant_window_ms = 800

    def emit(
        self,
        event_name: str,
        *,
        turn_id: str | None = None,
        provider: str | None = None,
        metadata: dict[str, Any] | None = None,
        once_per_turn: bool = False,
    ) -> dict[str, Any] | None:
        selected_turn_id = turn_id if turn_id is not None else self.current_turn_id
        if once_per_turn and selected_turn_id:
            key = (selected_turn_id, event_name)
            if key in self._seen_by_turn:
                return None
            self._seen_by_turn.add(key)

        event = self.logger.emit(
            event_name,
            turn_id=selected_turn_id,
            provider=provider,
            metadata=metadata or {},
        ).to_dict()
        self.events.append(event)
        return event

    def has_seen_event(self, turn_id: str, event_name: str) -> bool:
        return (turn_id, event_name) in self._seen_by_turn

    def set_llm_provider(self, provider: str, model: str) -> None:
        self.llm_provider = provider
        self.llm_model = model

    def configure_turn_policy(
        self,
        *,
        assistant_min_speak_ms_before_barge_in: int,
        barge_in_min_speech_ms: int,
        barge_in_min_transcript_words: int,
        mute_user_while_bot_speaking: bool,
        hard_interrupt_phrases: str | tuple[str, ...] | list[str],
        utterance_split_window_ms: int,
        user_resume_after_assistant_window_ms: int,
    ) -> None:
        self.assistant_min_speak_ms_before_barge_in = max(
            0, int(assistant_min_speak_ms_before_barge_in)
        )
        self.barge_in_min_speech_ms = max(0, int(barge_in_min_speech_ms))
        self.barge_in_min_transcript_words = max(1, int(barge_in_min_transcript_words))
        self.mute_user_while_bot_speaking = bool(mute_user_while_bot_speaking)
        self.hard_interrupt_phrases = tuple(
            phrase
            for raw in (
                hard_interrupt_phrases
                if isinstance(hard_interrupt_phrases, (tuple, list))
                else str(hard_interrupt_phrases).split(",")
            )
            if (phrase := str(raw).strip().lower())
        )
        self.utterance_split_window_ms = max(0, int(utterance_split_window_ms))
        self.user_resume_after_assistant_window_ms = max(
            0, int(user_resume_after_assistant_window_ms)
        )

    def mark_next_llm_start(self, turn_id: str, reason: str) -> None:
        self._llm_start_reason_by_turn[turn_id] = reason

    def cancel_active_generation(self, *, reason: str, turn_id: str | None = None) -> None:
        active_turn_id = self._llm_active_turn_id
        selected_turn_id = turn_id or active_turn_id or self.current_turn_id
        metadata = {
            "reason": reason,
            "active_llm_turn_id": active_turn_id,
            "assistant_speaking": self._assistant_speaking,
        }
        if active_turn_id:
            self._cancelled_llm_turn_ids.add(active_turn_id)
            if reason in {
                "user_started_speaking",
                "stt_during_active_llm",
                "user_continued_before_audio",
                "hard_interrupt_phrase",
                "sustained_user_speech",
                "transcript_word_threshold",
            }:
                self._pending_pipeline_interrupts.append(reason)
            self.emit(
                "llm.active_cancelled",
                turn_id=active_turn_id,
                provider="pipeline",
                metadata={**metadata, "active_llm_cancelled": True},
                once_per_turn=True,
            )
            self.emit(
                "llm.cancel_requested",
                turn_id=active_turn_id,
                provider="pipeline",
                metadata=metadata,
                once_per_turn=True,
            )
        if selected_turn_id:
            self.emit(
                "tts.cancel_requested",
                turn_id=selected_turn_id,
                provider="pipeline",
                metadata=metadata,
                once_per_turn=True,
            )

    def consume_pending_pipeline_interrupt(self) -> str | None:
        if not self._pending_pipeline_interrupts:
            return None
        return self._pending_pipeline_interrupts.popleft()

    def should_suppress_user_echo(self, frame: Any, *, echo_suppression_ms: int) -> bool:
        if echo_suppression_ms <= 0:
            return False
        frame_type = frame.__class__.__name__
        if frame_type not in {
            "UserStartedSpeakingFrame",
            "UserStoppedSpeakingFrame",
            "VADUserStartedSpeakingFrame",
            "VADUserStoppedSpeakingFrame",
            "InterimTranscriptionFrame",
            "TranscriptionFrame",
        }:
            return False
        if self._assistant_speaking:
            return True
        if self._last_assistant_audio_ms is None:
            return False
        return (time.monotonic() * 1000) - self._last_assistant_audio_ms <= echo_suppression_ms

    def handle_echo_suppressed(self, frame: Any, *, stage: str | None = None) -> None:
        metadata = _frame_metadata(frame)
        if stage:
            metadata["stage"] = stage
        self.emit(
            "audio.echo_suppressed",
            turn_id=self.current_turn_id or self._last_completed_turn_id,
            provider="pipeline",
            metadata=metadata,
        )

    def should_drop_frame(self, frame: Any, *, stage: str | None = None) -> bool:
        if id(frame) in self._drop_frame_ids:
            return True
        frame_type = frame.__class__.__name__
        if stage != "verbatim-llm-events" or frame_type not in {"LLMTextFrame", "TextFrame"}:
            return False
        active_turn_id = self._llm_active_turn_id
        return bool(active_turn_id and active_turn_id in self._cancelled_llm_turn_ids)

    def handle_llm_raw_token(self, text: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        self.handle_llm_stream_chunk(text, metadata)

    def handle_llm_stream_chunk(
        self,
        text: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        turn_id = self._llm_active_turn_id or self.current_turn_id or self.ensure_turn()
        event_metadata = {**self._llm_metadata(), **(metadata or {})}
        if text:
            event_metadata = {**event_metadata, "text_preview": text[:240]}
        self.emit(
            "llm.raw_token",
            turn_id=turn_id,
            provider=self.llm_provider,
            metadata=event_metadata,
        )
        self.emit(
            "llm.provider_first_chunk",
            turn_id=turn_id,
            provider=self.llm_provider,
            metadata=event_metadata,
            once_per_turn=True,
        )
        self.emit(
            "llm.first_raw_token",
            turn_id=turn_id,
            provider=self.llm_provider,
            metadata=event_metadata,
            once_per_turn=True,
        )
        self.emit(
            "llm.first_token",
            turn_id=turn_id,
            provider=self.llm_provider,
            metadata=event_metadata,
            once_per_turn=True,
        )

    def handle_first_speakable_phrase_sent(self, text: str, *, reason: str) -> None:
        turn_id = self._llm_active_turn_id or self.current_turn_id
        if not turn_id:
            return
        metadata = {
            **self._llm_metadata(),
            "text_preview": text[:240],
            "word_count": str(len(WORD_RE.findall(text))),
            "reason": reason,
        }
        self.emit(
            "llm.first_speakable_phrase",
            turn_id=turn_id,
            provider=self.llm_provider,
            metadata=metadata,
            once_per_turn=True,
        )
        self.emit(
            "tts.first_speakable_phrase_sent",
            turn_id=turn_id,
            provider=self._tts_provider(),
            metadata=metadata,
            once_per_turn=True,
        )

    def handle_tts_request(self, context_id: str, text: str) -> None:
        metadata = {
            "context_id": context_id,
            "text_preview": text[:240],
            "text_length": len(text),
            **self._llm_metadata(),
        }
        turn_id = self.current_turn_id
        if not turn_id:
            self.emit(
                "turn.phantom_prevented",
                turn_id=self._last_completed_turn_id,
                provider="pipeline",
                metadata={**metadata, "phantom_turn_prevented": True, "source": "tts_request"},
                once_per_turn=bool(self._last_completed_turn_id),
            )
            return
        self.emit(
            "tts.first_text_received",
            turn_id=turn_id,
            provider=self._tts_provider(),
            metadata=metadata,
            once_per_turn=True,
        )
        self.emit(
            "tts.text_received",
            turn_id=turn_id,
            provider=self._tts_provider(),
            metadata=metadata,
            once_per_turn=True,
        )
        self.emit(
            "tts.request_started",
            turn_id=turn_id,
            provider=self._tts_provider(),
            metadata=metadata,
            once_per_turn=True,
        )

    def start_session(self) -> None:
        self.emit("session.created")
        self.emit("session.started")

    def end_session(self, outcome: str = "completed") -> None:
        self.emit("session.ended", metadata={"outcome": outcome})
        self.write_call_summary(outcome=outcome)

    def ensure_turn(self) -> str:
        if self.current_turn_id is None:
            self.turn_index += 1
            self.current_turn_id = f"turn_{self.turn_index:04d}"
        return self.current_turn_id

    def complete_turn(self, outcome: str = "success") -> None:
        if self.current_turn_id is None:
            return
        event_name = "turn.completed" if outcome == "success" else f"turn.{outcome}"
        self.emit(event_name, turn_id=self.current_turn_id, once_per_turn=True)
        self.write_call_summary(outcome="active")
        self._last_completed_turn_id = self.current_turn_id
        self.current_turn_id = None

    def _active_turn_or_prevent_phantom(
        self,
        frame: Any,
        metadata: dict[str, Any],
    ) -> str | None:
        if self.current_turn_id:
            return self.current_turn_id

        frame_id = id(frame)
        if frame_id not in self._phantom_prevented_frame_ids:
            self._phantom_prevented_frame_ids.add(frame_id)
            self.emit(
                "turn.phantom_prevented",
                turn_id=self._last_completed_turn_id,
                provider="pipeline",
                metadata={**metadata, "phantom_turn_prevented": True},
                once_per_turn=bool(self._last_completed_turn_id),
            )
        return None

    def write_call_summary(self, *, outcome: str) -> None:
        summary = summarize_call_events(self.events, call_id=self.logger.call_id)
        summary["session_id"] = self.logger.session_id
        summary["agent_id"] = self.logger.agent_id
        summary["client_id"] = self.logger.client_id
        summary["outcome"] = outcome
        self.logger.write_call_summary(summary)
        self._write_slow_turn_traces(summary)

    def record_transcript(
        self,
        *,
        role: str,
        turn_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        item = {
            "schema_version": "0.1",
            "session_id": self.logger.session_id,
            "call_id": self.logger.call_id,
            "turn_id": turn_id,
            "agent_id": self.logger.agent_id,
            "client_id": self.logger.client_id,
            "role": role,
            "text": text,
            "timestamp_wall_iso": datetime.now(UTC).isoformat(),
            "metadata": metadata or {},
        }
        self.logger.write_transcript(item)

    def handle_transport_event(
        self,
        event_name: str,
        *,
        provider: str = "daily",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.emit(event_name, provider=provider, metadata=metadata or {})

    def handle_user_turn_stopped(self, content: str | None, metadata: dict[str, Any] | None = None) -> None:
        if not content:
            return
        turn_id = self.ensure_turn()
        if turn_id in self._user_transcripts:
            return
        self._user_transcripts[turn_id] = content
        self.record_transcript(role="user", turn_id=turn_id, text=content, metadata=metadata)

    def handle_assistant_turn_stopped(
        self,
        content: str | None,
        *,
        interrupted: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        turn_id = self.current_turn_id
        if not turn_id:
            return
        content = self._assistant_final_transcripts.pop(turn_id, None) or content
        if content:
            self.record_transcript(role="assistant", turn_id=turn_id, text=content, metadata=metadata)
        if interrupted:
            self.emit("assistant.interrupted", turn_id=turn_id)
            self.complete_turn("interrupted")
        else:
            self.complete_turn("success")

    def handle_assistant_final_transcript(
        self,
        text: str | None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        cleaned = " ".join(str(text or "").split())
        if not cleaned:
            return
        turn_id = self.current_turn_id or self._llm_active_turn_id or self.ensure_turn()
        self._assistant_final_transcripts[turn_id] = cleaned
        self.emit(
            "assistant.final_transcript",
            turn_id=turn_id,
            provider=self._tts_provider(),
            metadata={
                **(metadata or {}),
                "text_preview": cleaned[:240],
                "source": "provider_final_transcript",
            },
            once_per_turn=True,
        )

    def _now_ms(self) -> float:
        return time.monotonic() * 1000

    def _assistant_spoken_ms(self, turn_id: str, now_ms: float) -> float | None:
        started = self._assistant_playback_started_ms_by_turn.get(turn_id)
        if started is None:
            return None
        return max(0.0, now_ms - started)

    def _has_assistant_playback_started(self, turn_id: str) -> bool:
        return turn_id in self._assistant_playback_started_ms_by_turn

    def _contains_hard_interrupt(self, text: str | None) -> bool:
        if not text:
            return False
        lowered = f" {text.lower()} "
        for phrase in self.hard_interrupt_phrases:
            pattern = r"(?<![A-Za-z0-9])" + re.escape(phrase) + r"(?![A-Za-z0-9])"
            if re.search(pattern, lowered):
                return True
        return False

    def _barge_in_decision(
        self,
        *,
        turn_id: str,
        text: str | None,
        now_ms: float,
        source: str,
    ) -> tuple[bool, str, dict[str, Any]]:
        spoken_ms = self._assistant_spoken_ms(turn_id, now_ms)
        speech_ms = (
            max(0.0, now_ms - self._candidate_user_speech_started_ms)
            if self._candidate_user_speech_started_ms is not None
            else 0.0
        )
        word_count = len(WORD_RE.findall(text or ""))
        metadata = {
            "source": source,
            "assistant_spoken_ms": round(spoken_ms, 3) if spoken_ms is not None else None,
            "user_speech_ms": round(speech_ms, 3),
            "word_count": word_count,
            "min_assistant_speak_ms": self.assistant_min_speak_ms_before_barge_in,
            "min_user_speech_ms": self.barge_in_min_speech_ms,
            "min_transcript_words": self.barge_in_min_transcript_words,
        }

        if self.mute_user_while_bot_speaking and (
            self._assistant_speaking or self._llm_active_turn_id == turn_id
        ):
            return False, "user_muted_while_bot_speaking", metadata

        if self._contains_hard_interrupt(text):
            return True, "hard_interrupt_phrase", metadata

        if self._llm_active_turn_id == turn_id and not self._has_assistant_playback_started(turn_id):
            return True, "user_continued_before_audio", metadata

        if spoken_ms is None:
            return False, "assistant_not_playing", metadata
        if spoken_ms < self.assistant_min_speak_ms_before_barge_in:
            return False, "assistant_min_speak_window", metadata
        if speech_ms >= self.barge_in_min_speech_ms:
            return True, "sustained_user_speech", metadata
        if word_count >= self.barge_in_min_transcript_words:
            return True, "transcript_word_threshold", metadata
        return False, "uncertain_noise", metadata

    def _mark_possible_barge_in(
        self,
        *,
        turn_id: str,
        reason: str,
        metadata: dict[str, Any],
        frame_id: int | None = None,
    ) -> None:
        if frame_id is not None:
            self._drop_frame_ids.add(frame_id)
        self.emit(
            "barge_in.possible",
            turn_id=turn_id,
            provider="pipeline",
            metadata={**metadata, "reason": reason, "possible_barge_in": True},
            once_per_turn=True,
        )
        if reason in {
            "assistant_min_speak_window",
            "uncertain_noise",
            "user_muted_while_bot_speaking",
        }:
            self.emit(
                "barge_in.false",
                turn_id=turn_id,
                provider="pipeline",
                metadata={**metadata, "reason": reason, "false_barge_in": True},
                once_per_turn=True,
            )

    def _mark_premature_assistant_start(
        self,
        *,
        turn_id: str,
        text: str | None,
        now_ms: float,
        metadata: dict[str, Any],
    ) -> None:
        playback_started_ms = self._assistant_playback_started_ms_by_turn.get(turn_id)
        if playback_started_ms is None:
            return
        resume_ms = now_ms - playback_started_ms
        if resume_ms > self.user_resume_after_assistant_window_ms:
            return
        if text and not _looks_like_continuation(text):
            return
        self.emit(
            "user.resumed_within_800ms_after_assistant_start",
            turn_id=turn_id,
            provider="pipeline",
            metadata={
                **metadata,
                "resume_after_assistant_ms": round(resume_ms, 3),
                "window_ms": self.user_resume_after_assistant_window_ms,
            },
            once_per_turn=True,
        )
        self.emit(
            "turn.premature_assistant_start",
            turn_id=turn_id,
            provider="pipeline",
            metadata={
                **metadata,
                "premature_assistant_start": True,
                "resume_after_assistant_ms": round(resume_ms, 3),
            },
            once_per_turn=True,
        )

    def _interrupt_active_turn(
        self,
        *,
        turn_id: str,
        reason: str,
        metadata: dict[str, Any],
    ) -> None:
        self.emit(
            "barge_in.valid",
            turn_id=turn_id,
            provider="pipeline",
            metadata={**metadata, "reason": reason, "valid_barge_in": True},
            once_per_turn=True,
        )
        if not self._assistant_speaking:
            self.emit(
                "barge_in.before_audio",
                turn_id=turn_id,
                provider="pipeline",
                metadata={**metadata, "barge_in_before_audio": True, "reason": reason},
                once_per_turn=True,
            )
        self.emit(
            "user.interrupted_assistant",
            turn_id=turn_id,
            metadata={**metadata, "reason": reason},
            once_per_turn=True,
        )
        self.emit(
            "assistant.interrupted",
            turn_id=turn_id,
            metadata={**metadata, "assistant_speech_cancelled_reason": reason},
            once_per_turn=True,
        )
        if self._assistant_speaking:
            self.emit(
                "voice.cutout_suspected",
                turn_id=turn_id,
                provider="pipeline",
                metadata={
                    **metadata,
                    "voice_cutout_suspected": True,
                    "assistant_speech_cancelled_reason": reason,
                },
                once_per_turn=True,
            )
        self.emit(
            "turn.interrupted",
            turn_id=turn_id,
            metadata={**metadata, "reason": reason},
            once_per_turn=True,
        )
        self.cancel_active_generation(reason=reason, turn_id=turn_id)
        if self.current_turn_id == turn_id:
            self.complete_turn("interrupted")
        else:
            self._last_completed_turn_id = turn_id

    def _detect_user_utterance_split(
        self,
        *,
        turn_id: str,
        text: str,
        now_ms: float,
        metadata: dict[str, Any],
    ) -> None:
        previous_turn_id = self._last_user_commit_turn_id
        previous_text = self._last_user_commit_text or ""
        previous_ms = self._last_user_commit_ms
        if (
            not previous_turn_id
            or previous_turn_id == turn_id
            or previous_ms is None
            or not previous_text
        ):
            return
        gap_ms = now_ms - previous_ms
        assistant_between = (
            self._assistant_playback_started_ms_by_turn.get(previous_turn_id) is not None
        )
        looks_continuous = (
            not _has_strong_terminal_punctuation(previous_text)
            or _looks_like_continuation(text)
        )
        if (
            gap_ms <= self.utterance_split_window_ms
            and assistant_between
            and looks_continuous
        ):
            self.emit(
                "turn.user_utterance_split",
                turn_id=turn_id,
                provider="pipeline",
                metadata={
                    **metadata,
                    "user_utterance_split": True,
                    "previous_turn_id": previous_turn_id,
                    "gap_ms": round(gap_ms, 3),
                    "window_ms": self.utterance_split_window_ms,
                    "previous_text_preview": previous_text[:160],
                    "text_preview": text[:160],
                },
                once_per_turn=True,
            )

    def _remember_user_commit(self, *, turn_id: str, text: str, now_ms: float) -> None:
        self._last_user_commit_turn_id = turn_id
        self._last_user_commit_text = text
        self._last_user_commit_ms = now_ms

    def handle_frame(self, frame: Any, *, stage: str | None = None) -> None:
        frame_type = frame.__class__.__name__
        metadata = _frame_metadata(frame)
        if stage:
            metadata["stage"] = stage

        if frame_type == "UserStartedSpeakingFrame":
            if not self._consume_frame_once(frame):
                return
            now_ms = self._now_ms()
            self._candidate_user_speech_started_ms = now_ms
            interrupted_turn_id = self._llm_active_turn_id or (
                self.current_turn_id if self._assistant_speaking else None
            )
            self._candidate_user_turn_id = interrupted_turn_id
            if interrupted_turn_id:
                allowed, reason, policy_metadata = self._barge_in_decision(
                    turn_id=interrupted_turn_id,
                    text=None,
                    now_ms=now_ms,
                    source="user_started_speaking",
                )
                event_metadata = {**metadata, **policy_metadata}
                self._mark_premature_assistant_start(
                    turn_id=interrupted_turn_id,
                    text=None,
                    now_ms=now_ms,
                    metadata=event_metadata,
                )
                if allowed:
                    self._interrupt_active_turn(
                        turn_id=interrupted_turn_id,
                        reason=reason,
                        metadata=event_metadata,
                    )
                else:
                    self._mark_possible_barge_in(
                        turn_id=interrupted_turn_id,
                        reason=reason,
                        metadata=event_metadata,
                        frame_id=id(frame),
                    )
            turn_id = self.ensure_turn()
            self.emit(
                "user.speech_started",
                turn_id=turn_id,
                metadata=metadata,
                once_per_turn=True,
            )
            return

        if frame_type == "VADUserStartedSpeakingFrame":
            if not self._consume_frame_once(frame):
                return
            turn_id = self.ensure_turn()
            self.emit("vad.user_speech_started", turn_id=turn_id, metadata=metadata, once_per_turn=True)
            return

        if frame_type == "VADUserStoppedSpeakingFrame":
            if not self._consume_frame_once(frame):
                return
            turn_id = self.ensure_turn()
            self.emit("vad.user_speech_stopped", turn_id=turn_id, metadata=metadata, once_per_turn=True)
            return

        if frame_type == "InterruptionFrame":
            if not self._consume_frame_once(frame):
                return
            interrupted_turn_id = self._llm_active_turn_id or self.current_turn_id
            if interrupted_turn_id:
                allowed, reason, policy_metadata = self._barge_in_decision(
                    turn_id=interrupted_turn_id,
                    text=None,
                    now_ms=self._now_ms(),
                    source="interruption_frame",
                )
                event_metadata = {**metadata, **policy_metadata}
                if not allowed:
                    self._mark_possible_barge_in(
                        turn_id=interrupted_turn_id,
                        reason=reason,
                        metadata=event_metadata,
                        frame_id=id(frame),
                    )
                    return
                self._interrupt_active_turn(
                    turn_id=interrupted_turn_id,
                    reason=reason,
                    metadata=event_metadata,
                )
            elif self.current_turn_id:
                self.emit(
                    "pipeline.interruption",
                    turn_id=self.current_turn_id,
                    provider="pipeline",
                    metadata=metadata,
                    once_per_turn=True,
                )
            return

        if frame_type == "UserStoppedSpeakingFrame":
            if not self._consume_frame_once(frame):
                return
            turn_id = self.ensure_turn()
            self.emit("user.speech_stopped", turn_id=turn_id, metadata=metadata, once_per_turn=True)
            return

        if frame_type == "InterimTranscriptionFrame":
            if self._llm_active_turn_id and self.current_turn_id == self._llm_active_turn_id:
                interrupted_turn_id = self._llm_active_turn_id
                text = _frame_text(frame)
                now_ms = self._now_ms()
                allowed, reason, policy_metadata = self._barge_in_decision(
                    turn_id=interrupted_turn_id,
                    text=text,
                    now_ms=now_ms,
                    source="interim_transcript_during_active_response",
                )
                event_metadata = {**metadata, **policy_metadata}
                self._mark_premature_assistant_start(
                    turn_id=interrupted_turn_id,
                    text=text,
                    now_ms=now_ms,
                    metadata=event_metadata,
                )
                if allowed:
                    if self.llm_provider == "ultravox":
                        self.emit(
                            "ultravox.barge_in_observed",
                            turn_id=interrupted_turn_id,
                            provider="ultravox",
                            metadata={**event_metadata, "managed_by": "ultravox"},
                            once_per_turn=True,
                        )
                    self._interrupt_active_turn(
                        turn_id=interrupted_turn_id,
                        reason=reason,
                        metadata=event_metadata,
                    )
                else:
                    self._mark_possible_barge_in(
                        turn_id=interrupted_turn_id,
                        reason=reason,
                        metadata=event_metadata,
                        frame_id=id(frame),
                    )
            turn_id = self.ensure_turn()
            result = getattr(frame, "result", None)
            provider = self._stt_provider_from_result(result)
            if isinstance(result, dict) and result.get("event") == "EagerEndOfTurn":
                self.emit(
                    "stt.eager_end_of_turn",
                    turn_id=turn_id,
                    provider="deepgram_flux",
                    metadata=metadata,
                    once_per_turn=True,
                )
            self.emit(
                "stt.first_interim",
                turn_id=turn_id,
                provider=provider,
                metadata=metadata,
                once_per_turn=True,
            )
            return

        if frame_type == "TranscriptionFrame":
            if self._llm_active_turn_id and self.current_turn_id == self._llm_active_turn_id:
                interrupted_turn_id = self._llm_active_turn_id
                text = _frame_text(frame)
                now_ms = self._now_ms()
                allowed, reason, policy_metadata = self._barge_in_decision(
                    turn_id=interrupted_turn_id,
                    text=text,
                    now_ms=now_ms,
                    source="final_transcript_during_active_response",
                )
                event_metadata = {**metadata, **policy_metadata}
                self._mark_premature_assistant_start(
                    turn_id=interrupted_turn_id,
                    text=text,
                    now_ms=now_ms,
                    metadata=event_metadata,
                )
                if allowed:
                    if self.llm_provider == "ultravox":
                        self.emit(
                            "ultravox.barge_in_observed",
                            turn_id=interrupted_turn_id,
                            provider="ultravox",
                            metadata={**event_metadata, "managed_by": "ultravox"},
                            once_per_turn=True,
                        )
                    self._interrupt_active_turn(
                        turn_id=interrupted_turn_id,
                        reason=reason,
                        metadata=event_metadata,
                    )
                else:
                    self._mark_possible_barge_in(
                        turn_id=interrupted_turn_id,
                        reason=reason,
                        metadata=event_metadata,
                        frame_id=id(frame),
                    )
                    return
            turn_id = self.ensure_turn()
            text = _frame_text(frame)
            now_ms = self._now_ms()
            result = getattr(frame, "result", None)
            provider = self._stt_provider_from_result(result)
            if isinstance(result, dict) and result.get("event") == "EndOfTurn":
                self.emit("user.speech_stopped", turn_id=turn_id, metadata=metadata, once_per_turn=True)
                self.emit(
                    "stt.utterance_end",
                    turn_id=turn_id,
                    provider="deepgram_flux",
                    metadata=metadata,
                    once_per_turn=True,
                )
            self.emit(
                "transcript.ready",
                turn_id=turn_id,
                provider=provider,
                metadata={**metadata, "source": "final"},
                once_per_turn=True,
            )
            self.emit(
                "stt.finalization",
                turn_id=turn_id,
                provider=provider,
                metadata=metadata,
                once_per_turn=True,
            )
            self.emit(
                "stt.final_transcript",
                turn_id=turn_id,
                provider=provider,
                metadata=metadata,
                once_per_turn=True,
            )
            self.emit("turn.user_committed", turn_id=turn_id, metadata=metadata, once_per_turn=True)
            if text:
                self._detect_user_utterance_split(
                    turn_id=turn_id,
                    text=text,
                    now_ms=now_ms,
                    metadata=metadata,
                )
                self.handle_user_turn_stopped(text, metadata=metadata)
                self._remember_user_commit(turn_id=turn_id, text=text, now_ms=now_ms)
            return

        if frame_type in {"LLMMessagesFrame", "LLMContextFrame", "LLMRunFrame"} or frame_type.endswith(
            ("LLMContextFrame", "MessagesFrame")
        ):
            turn_id = self.ensure_turn()
            reason = self._llm_start_reason_by_turn.get(turn_id) or self._infer_llm_start_reason(turn_id)
            self._llm_start_reason_by_turn[turn_id] = reason
            queue_metadata = self._llm_queue_metadata(turn_id)
            self.emit(
                "llm.enqueued",
                turn_id=turn_id,
                provider=self.llm_provider,
                metadata={
                    **metadata,
                    **self._llm_metadata(),
                    **queue_metadata,
                    "llm_started_reason": reason,
                },
                once_per_turn=True,
            )
            self._llm_active_turn_id = self._llm_active_turn_id or turn_id
            return

        if frame_type == "LLMFullResponseStartFrame":
            turn_id = self.ensure_turn()
            reason = self._llm_start_reason_by_turn.get(turn_id) or self._infer_llm_start_reason(turn_id)
            if not self.has_seen_event(turn_id, "llm.enqueued"):
                self.emit(
                    "llm.enqueued",
                    turn_id=turn_id,
                    provider=self.llm_provider,
                    metadata={
                        **metadata,
                        **self._llm_metadata(),
                        **self._llm_queue_metadata(turn_id),
                        "llm_started_reason": reason,
                        "source": "implicit",
                    },
                    once_per_turn=True,
                )
            self._llm_active_turn_id = turn_id
            self.emit(
                "llm.request_started",
                turn_id=turn_id,
                provider=self.llm_provider,
                metadata={
                    **metadata,
                    **self._llm_metadata(),
                    **self._llm_queue_metadata(turn_id),
                    "llm_started_reason": reason,
                },
                once_per_turn=True,
            )
            return

        if frame_type in {"LLMTextFrame", "TextFrame"}:
            turn_id = self._llm_active_turn_id or self.current_turn_id or self.ensure_turn()
            if turn_id in self._cancelled_llm_turn_ids:
                self.emit(
                    "llm.stale_text_dropped",
                    turn_id=turn_id,
                    provider=self.llm_provider,
                    metadata={**metadata, **self._llm_metadata()},
                    once_per_turn=True,
                )
                return
            text = _frame_text(frame)
            self.emit(
                "llm.first_text_chunk",
                turn_id=turn_id,
                provider=self.llm_provider,
                metadata={**metadata, **self._llm_metadata()},
                once_per_turn=True,
            )
            self.emit(
                "llm.first_text_frame_emitted",
                turn_id=turn_id,
                provider=self.llm_provider,
                metadata={**metadata, **self._llm_metadata()},
                once_per_turn=True,
            )
            self.emit(
                "llm.text_frame_emitted",
                turn_id=turn_id,
                provider=self.llm_provider,
                metadata={**metadata, **self._llm_metadata()},
                once_per_turn=True,
            )
            if text:
                self._assistant_chunks.setdefault(turn_id, []).append(text)
                accumulated = "".join(self._assistant_chunks.get(turn_id, []))
                words = WORD_RE.findall(accumulated)
                word_metadata = {
                    **metadata,
                    **self._llm_metadata(),
                    "word_count": str(len(words)),
                    "text_preview": accumulated[:240],
                }
                if len(words) >= 3:
                    self.emit(
                        "llm.time_to_3_words",
                        turn_id=turn_id,
                        provider=self.llm_provider,
                        metadata=word_metadata,
                        once_per_turn=True,
                    )
                if len(words) >= 6:
                    self.emit(
                        "llm.time_to_6_words",
                        turn_id=turn_id,
                        provider=self.llm_provider,
                        metadata=word_metadata,
                        once_per_turn=True,
                    )
                if any(mark in accumulated for mark in ".!?"):
                    self.emit(
                        "llm.first_punctuation",
                        turn_id=turn_id,
                        provider=self.llm_provider,
                        metadata=word_metadata,
                        once_per_turn=True,
                    )
                if len(words) >= 3 or any(mark in accumulated for mark in ".!?"):
                    self.emit(
                        "llm.first_speakable_phrase",
                        turn_id=turn_id,
                        provider=self.llm_provider,
                        metadata=word_metadata,
                        once_per_turn=True,
                    )
                if any(mark in accumulated for mark in ".!?"):
                    self.emit(
                        "llm.first_sentence",
                        turn_id=turn_id,
                        provider=self.llm_provider,
                        metadata={**metadata, **self._llm_metadata()},
                        once_per_turn=True,
                    )
                self.emit(
                    "tts.first_text_sent",
                    turn_id=turn_id,
                    provider=self._tts_provider(),
                    metadata={**metadata, **self._llm_metadata()},
                    once_per_turn=True,
                )
            return

        if frame_type == "LLMFullResponseEndFrame":
            turn_id = self._llm_active_turn_id or self.current_turn_id
            if not turn_id:
                self._active_turn_or_prevent_phantom(frame, metadata)
                return
            if turn_id in self._cancelled_llm_turn_ids:
                self.emit(
                    "llm.stale_completed",
                    turn_id=turn_id,
                    provider=self.llm_provider,
                    metadata={**metadata, **self._llm_metadata(), "stale_llm_completed": True},
                    once_per_turn=True,
                )
            self.emit(
                "llm.completed",
                turn_id=turn_id,
                provider=self.llm_provider,
                metadata={**metadata, **self._llm_metadata()},
                once_per_turn=True,
            )
            if self._llm_active_turn_id == turn_id:
                self._llm_active_turn_id = None
            return

        if frame_type in {"TTSStartedFrame", "TTSStartFrame"}:
            turn_id = self._active_turn_or_prevent_phantom(frame, metadata)
            if not turn_id:
                return
            self.emit(
                "tts.request_started",
                turn_id=turn_id,
                provider=self._tts_provider(),
                metadata=metadata,
                once_per_turn=True,
            )
            return

        if frame_type in {"TTSAudioRawFrame", "TTSRawAudioFrame", "OutputAudioRawFrame"}:
            turn_id = self._active_turn_or_prevent_phantom(frame, metadata)
            if not turn_id:
                return
            self._last_assistant_audio_ms = time.monotonic() * 1000
            self._assistant_playback_started_ms_by_turn.setdefault(
                turn_id, self._last_assistant_audio_ms
            )
            self.emit(
                "tts.first_audio_chunk",
                turn_id=turn_id,
                provider=self._tts_provider(),
                metadata=metadata,
                once_per_turn=True,
            )
            self.emit(
                "tts.first_playable_audio",
                turn_id=turn_id,
                provider=self._tts_provider(),
                metadata=metadata,
                once_per_turn=True,
            )
            self.emit("assistant.playback_started", turn_id=turn_id, metadata=metadata, once_per_turn=True)
            return

        if frame_type in {"TTSStoppedFrame", "TTSStopFrame"}:
            turn_id = self._active_turn_or_prevent_phantom(frame, metadata)
            if not turn_id:
                return
            self.emit(
                "tts.completed",
                turn_id=turn_id,
                provider=self._tts_provider(),
                metadata=metadata,
                once_per_turn=True,
            )
            return

        if frame_type == "BotStartedSpeakingFrame":
            if not self._consume_frame_once(frame):
                return
            turn_id = self._active_turn_or_prevent_phantom(frame, metadata)
            if not turn_id:
                return
            self._assistant_speaking = True
            self._last_assistant_audio_ms = time.monotonic() * 1000
            self._assistant_playback_started_ms_by_turn.setdefault(
                turn_id, self._last_assistant_audio_ms
            )
            self.emit("assistant.playback_started", turn_id=turn_id, metadata=metadata, once_per_turn=True)
            self.emit("assistant.speech_started", turn_id=turn_id, metadata=metadata, once_per_turn=True)
            return

        if frame_type == "BotStoppedSpeakingFrame":
            if not self._consume_frame_once(frame):
                return
            turn_id = self._active_turn_or_prevent_phantom(frame, metadata)
            if not turn_id:
                self._assistant_speaking = False
                self._last_assistant_audio_ms = time.monotonic() * 1000
                return
            self._assistant_speaking = False
            self._last_assistant_audio_ms = time.monotonic() * 1000
            self.emit("assistant.speech_completed", turn_id=turn_id, metadata=metadata, once_per_turn=True)
            content = "".join(self._assistant_chunks.get(turn_id, [])).strip()
            self.handle_assistant_turn_stopped(content, metadata=metadata)
            return

        if frame_type == "ErrorFrame":
            turn_id = self.current_turn_id
            provider = str(getattr(frame, "processor", None) or "unknown").lower()
            self.emit("turn.failed", turn_id=turn_id, provider=provider, metadata=metadata)
            self.write_call_summary(outcome="failed")
            return

        if frame_type == "MetricsFrame":
            self.handle_metrics_frame(frame)

    def _consume_frame_once(self, frame: Any) -> bool:
        frame_id = id(frame)
        if frame_id in self._seen_frame_ids:
            return False
        if len(self._seen_frame_id_order) == self._seen_frame_id_order.maxlen:
            expired = self._seen_frame_id_order.popleft()
            self._seen_frame_ids.discard(expired)
        self._seen_frame_ids.add(frame_id)
        self._seen_frame_id_order.append(frame_id)
        return True

    def _llm_queue_metadata(self, turn_id: str) -> dict[str, Any]:
        active_turn_id = self._llm_active_turn_id
        return {
            "queue_depth": 1 if active_turn_id and active_turn_id != turn_id else 0,
            "old_llm_running": bool(active_turn_id and active_turn_id != turn_id),
            "active_llm_turn_id": active_turn_id,
        }

    def _llm_metadata(self) -> dict[str, Any]:
        return {
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
        }

    def _tts_provider(self) -> str:
        return "ultravox" if self.llm_provider == "ultravox" else "cartesia"

    def _stt_provider_from_result(self, result: Any) -> str:
        if self.llm_provider == "ultravox":
            return "ultravox"
        return "deepgram_flux" if isinstance(result, dict) and result.get("event") else "deepgram"

    def _write_slow_turn_traces(self, summary: dict[str, Any]) -> None:
        threshold = summary.get("p95_transcript_ready_to_playback_ms") or summary.get(
            "p95_perceived_latency_ms"
        )
        if threshold is None:
            return
        for turn in summary.get("turns", []):
            latency = turn.get("latency") or {}
            observed = latency.get("transcript_ready_to_playback_ms") or latency.get(
                "perceived_response_latency_ms"
            )
            if observed is None or observed < threshold:
                continue
            turn_id = turn.get("turn_id")
            if not turn_id:
                continue
            turn_events = [event for event in self.events if event.get("turn_id") == turn_id]
            self.logger.write_slow_turn_trace(
                str(turn_id),
                self._slow_turn_trace_payload(summary, turn, turn_events),
            )

    def _slow_turn_trace_payload(
        self,
        summary: dict[str, Any],
        turn: dict[str, Any],
        turn_events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        timestamps = turn.get("timestamps") or {}
        numeric_timestamps = [
            value for value in timestamps.values() if isinstance(value, (int, float))
        ]
        base = min(numeric_timestamps) if numeric_timestamps else None
        relative_timeline = {
            key: round(value - base, 3) if isinstance(value, (int, float)) and base is not None else None
            for key, value in timestamps.items()
        }
        user_text = _first_event_text(turn_events, {"stt.final_transcript", "transcript.ready"})
        response_text = " ".join(
            text
            for event in turn_events
            if event.get("event_name") in {"llm.text_frame_emitted", "llm.first_text_chunk"}
            and (text := str((event.get("metadata") or {}).get("text_preview") or "").strip())
        )
        return {
            "schema_version": "0.1",
            "call_id": self.logger.call_id,
            "session_id": self.logger.session_id,
            "turn_id": turn.get("turn_id"),
            "dominant_bottleneck": turn.get("dominant_bottleneck"),
            "slowest_stage": turn.get("slowest_stage"),
            "outcome": turn.get("outcome"),
            "latency": turn.get("latency") or {},
            "timeline": relative_timeline,
            "timestamps": timestamps,
            "transcript": user_text,
            "response_text_preview": response_text[:480],
            "llm_provider": turn.get("llm_provider") or summary.get("llm_provider"),
            "llm_model": turn.get("llm_model") or summary.get("llm_model"),
            "transport_provider": summary.get("transport_provider"),
            "room_name": summary.get("room_name"),
            "config_snapshot": summary.get("config_snapshot") or {},
            "events": turn_events,
        }

    def _infer_llm_start_reason(self, turn_id: str) -> str:
        if self.has_seen_event(turn_id, "stt.eager_end_of_turn") and not self.has_seen_event(
            turn_id, "turn.user_committed"
        ):
            return "eager"
        if self.has_seen_event(turn_id, "turn.user_committed") or self.has_seen_event(
            turn_id, "stt.final_transcript"
        ):
            return "final"
        return "manual"

    def handle_metrics_frame(self, frame: Any) -> None:
        metric_items = getattr(frame, "data", None) or getattr(frame, "metrics", None) or []
        for metric in metric_items:
            metric_type = metric.__class__.__name__
            provider = _provider_from_metric(metric)
            if provider == "openai" and self.llm_provider in {"groq", "qwen", "xai"}:
                provider = self.llm_provider
            metadata = {"metric_type": metric_type}
            for attr in (
                "processor",
                "model",
                "value",
                "ttfb",
                "duration",
                "tokens",
                "prompt_tokens",
                "completion_tokens",
                "characters",
            ):
                value = getattr(metric, attr, None)
                if value is not None:
                    metadata[attr] = str(value)
            self.emit("metrics.observed", provider=provider, metadata=metadata)


def _provider_from_metric(metric: Any) -> str | None:
    text = f"{metric.__class__.__name__} {getattr(metric, 'processor', '')}".lower()
    if "flux" in text:
        return "deepgram_flux"
    if "deepgram" in text:
        return "deepgram"
    if "google" in text or "gemini" in text:
        return "gemini"
    if "openai" in text:
        return "openai"
    if "qwen" in text:
        return "qwen"
    if "xai" in text or "grok" in text:
        return "xai"
    if "groq" in text:
        return "groq"
    if "ultravox" in text:
        return "ultravox"
    if "cartesia" in text:
        return "cartesia"
    if "daily" in text:
        return "daily"
    return None


def _first_event_text(events: list[dict[str, Any]], event_names: set[str]) -> str | None:
    for event in events:
        if event.get("event_name") not in event_names:
            continue
        text = (event.get("metadata") or {}).get("text_preview") or (
            event.get("metadata") or {}
        ).get("transcript")
        if text:
            return str(text)
    return None


CONTINUATION_START_WORDS = {
    "actually",
    "also",
    "and",
    "because",
    "but",
    "except",
    "if",
    "like",
    "plus",
    "so",
    "then",
    "though",
    "well",
}


def _has_strong_terminal_punctuation(text: str) -> bool:
    return text.strip().rstrip("\"')]").endswith((".", "?", "!"))


def _looks_like_continuation(text: str | None) -> bool:
    if not text:
        return True
    words = WORD_RE.findall(text.lower())
    if not words:
        return True
    if words[0] in CONTINUATION_START_WORDS:
        return True
    return len(words) <= 2 and words[0] not in {"stop", "wait", "no", "bye", "hello", "hi"}


def make_session_ids() -> tuple[str, str]:
    return new_id("sess"), new_id("call")
