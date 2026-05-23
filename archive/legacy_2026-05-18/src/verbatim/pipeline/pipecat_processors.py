from __future__ import annotations

import asyncio
import re
from typing import Any

from verbatim.instrumentation.recorder import CallRecorder


WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)?")
DANGLING_FINAL_WORDS = {
    "a",
    "about",
    "an",
    "and",
    "because",
    "but",
    "by",
    "for",
    "from",
    "if",
    "in",
    "into",
    "like",
    "of",
    "or",
    "that",
    "the",
    "to",
    "unless",
    "with",
    "you",
}
FRAGMENT_FINAL_WORDS = DANGLING_FINAL_WORDS | {
    "also",
    "actually",
    "basically",
    "kind",
    "maybe",
    "really",
    "said",
    "so",
    "then",
    "um",
    "uh",
    "well",
}
SHORT_COMPLETE_UTTERANCES = {
    "bye",
    "goodbye",
    "hello",
    "hey",
    "hi",
    "no",
    "nope",
    "okay",
    "sure",
    "thanks",
    "thank you",
    "yes",
    "yep",
}
RECAP_SENTENCE_RE = re.compile(
    r"^\s*(?:oh[, ]+|okay[, ]+|okay so[, ]+|alright[, ]+|right[, ]+)?"
    r"(?:it sounds like|sounds like|you(?:'re| are| were| want| need| have| mentioned| said| told me)|"
    r"you(?:'re| are)\s+looking(?:\s+to|\s+for)?)\b[^.?!]{0,180}[.?!]\s*",
    re.IGNORECASE,
)
RECAP_COMMA_RE = re.compile(
    r"^\s*(?:oh[, ]+|okay[, ]+|okay so[, ]+|alright[, ]+|right[, ]+)?"
    r"(?:you(?:'re| are| were| want| need| have)|you(?:'re| are)\s+looking(?:\s+to|\s+for)?)"
    r"\b[^,.;?!]{0,180},\s*",
    re.IGNORECASE,
)
BUDGET_PRAISE_RE = re.compile(
    r"^\s*(?:that(?:'s| is)|it(?:'s| is))\s+(?:a\s+)?"
    r"(?:great|good|solid|nice|healthy|big|strong|reasonable|flexible)\s+"
    r"(?:budget|income|range|number)\b[^.?!]*[.?!]\s*",
    re.IGNORECASE,
)
OPTION_PRAISE_RE = re.compile(
    r"^\s*(?:you (?:can|could|will)|that (?:can|could|will)|this (?:can|could|will))\b"
    r"[^.?!]*(?:lot of|plenty of|many|different)\s+(?:properties|options|places)\b[^.?!]*[.?!]\s*",
    re.IGNORECASE,
)
DUBAI_FILLER_RE = re.compile(
    r"^\s*(?:(?:luxury\s+)?properties in Dubai|Dubai(?:'s)?\s+(?:property|real estate|market|properties)|"
    r"Dubai\s+(?:has|offers|can|is|gives))\b[^.?!]*[.?!]\s*",
    re.IGNORECASE,
)
PERSONAL_ANECDOTE_RE = re.compile(
    r"\b(?:just got back from|morning walk|evening walk|by the Dubai Marina|"
    r"my day (?:is|was)|my morning (?:is|was))\b[^.?!]*[.?!]?\s*",
    re.IGNORECASE,
)
MARKET_CLICHE_RE = re.compile(
    r"\b(?:villas and apartments have their own charm|"
    r"investing in Dubai property can be a great move|"
    r"Dubai properties often have high rental yields|"
    r"(?:luxury\s+)?properties in Dubai can be stunning)\b[^.?!]*[.?!]?\s*",
    re.IGNORECASE,
)
GENERIC_QUESTION_REPLACEMENTS = (
    (
        re.compile(
            r"\bwhat(?:'s| is)?\s+your\s+budget(?:\s+for\s+[^?]{1,60})?\??",
            re.IGNORECASE,
        ),
        "We can keep the budget flexible.",
    ),
    (
        re.compile(
            r"\bwhat\s+areas?\s+(?:are|were)\s+you\s+looking\s+at(?:\s+in\s+Dubai)?\??",
            re.IGNORECASE,
        ),
        "We can keep the area broad for now.",
    ),
    (
        re.compile(r"\bare\s+you\s+looking\s+for\s+a\s+villa\s+or\s+an?\s+apartment\??", re.IGNORECASE),
        "I can send both villas and apartments.",
    ),
    (
        re.compile(
            r"\bwhat\s+(?:type|kind)\s+of\s+property\s+are\s+you\s+(?:interested\s+in|thinking\s+of)\??",
            re.IGNORECASE,
        ),
        "I can send a few directions on WhatsApp.",
    ),
    (
        re.compile(
            r"\bwhat\s+(?:type|kind)\s+of\s+(?:house|home|place|property)\s+are\s+you\s+looking\s+for\??",
            re.IGNORECASE,
        ),
        "Tell me a bit more.",
    ),
    (
        re.compile(r"\bwhat(?:'s| is)\s+on\s+your\s+mind\??", re.IGNORECASE),
        "Tell me a bit more.",
    ),
    (
        re.compile(r"\bwhat\s+(?:type|kind)\s+of\s+location\s+are\s+you\s+thinking\s+of\??", re.IGNORECASE),
        "We can keep the area broad for now.",
    ),
    (
        re.compile(r"\bhow\s+many\s+bedrooms\s+are\s+they\s+looking\s+for\??", re.IGNORECASE),
        "I can get the details on WhatsApp.",
    ),
    (
        re.compile(r"\bwould\s+you\s+like\s+to\s+save\s+your\s+contact\s+info\s+for\s+future\s+inquiries\??", re.IGNORECASE),
        "I'll follow up on WhatsApp.",
    ),
    (
        re.compile(r"\bwhat(?:'s| is)?\s+your\s+priority\b[^?]*\??", re.IGNORECASE),
        "I can send a few directions on WhatsApp.",
    ),
    (
        re.compile(
            r"\bare\s+you\s+looking\s+to\s+rent\s+or\s+buy(?:\s+(?:a\s+)?(?:property|place|home|apartment|villa))?(?:\s+in\s+Dubai)?\??",
            re.IGNORECASE,
        ),
        "We can figure rent or purchase later.",
    ),
    (
        re.compile(r"\bare\s+you\s+looking\s+to\s+rent\s+(?:in\s+Dubai\s*)?\??", re.IGNORECASE),
        "We can figure rent or purchase later.",
    ),
    (
        re.compile(
            r"\bwhat\s+property\s+(?:are|were)\s+(?:we|you)\s+looking\s+at\??",
            re.IGNORECASE,
        ),
        "No rush, we can just talk first.",
    ),
)

MODE_INSTRUCTIONS = {
    "social": (
        "Conversation mode: social. Answer the social/check-in only. "
        "Do not invent personal experiences or mention walks, Marina, your day, budget, "
        "area, rent, purchase, property type, or listings."
    ),
    "capability_explanation": (
        "Conversation mode: capability_explanation. Explain briefly what Alicia can help with "
        "in one natural sentence. Do not start qualifying the caller."
    ),
    "appointment_booking": (
        "Conversation mode: appointment_booking. Ask for exactly one appointment detail only, "
        "or offer WhatsApp follow-up if the detail is not essential."
    ),
    "property_interest": (
        "Conversation mode: property_interest. Be helpful and relaxed. No market praise or "
        "generic Dubai facts. Ask one soft next step only if truly needed; otherwise offer "
        "to send grounded options on WhatsApp."
    ),
    "human_handoff": (
        "Conversation mode: human_handoff. Offer WhatsApp follow-up and stop probing."
    ),
    "repeat": (
        "Conversation mode: repeat. Repeat the previous useful answer, shorter."
    ),
    "stop_or_correction": (
        "Conversation mode: stop_or_correction. Apologize briefly, stop the current flow, "
        "and do not ask a property question."
    ),
    "goodbye": (
        "Conversation mode: goodbye. Close warmly and briefly."
    ),
    "unknown": (
        "Conversation mode: unknown. Answer briefly. If uncertain, offer WhatsApp follow-up "
        "instead of asking multiple questions."
    ),
}

MODE_KEYWORDS = {
    "stop_or_correction": (
        "stop",
        "wait",
        "hold on",
        "let me finish",
        "chill",
        "don't ask",
        "do not ask",
        "actually",
        "no question",
    ),
    "human_handoff": (
        "human",
        "person",
        "real agent",
        "someone",
        "whatsapp",
        "call me",
        "message me",
    ),
    "repeat": (
        "repeat",
        "say that again",
        "what did you say",
        "again",
    ),
    "goodbye": (
        "bye",
        "goodbye",
        "take care",
        "that's all",
        "thats all",
        "end the call",
    ),
    "appointment_booking": (
        "book",
        "booking",
        "schedule",
        "viewing",
        "appointment",
        "visit",
        "tour",
    ),
    "capability_explanation": (
        "what can you help",
        "what do you do",
        "how can you help",
        "who are you",
    ),
    "social": (
        "hello",
        "hi",
        "hey",
        "how are you",
        "nice to meet you",
        "can you hear me",
        "what's your name",
        "whats your name",
    ),
    "property_interest": (
        "property",
        "apartment",
        "villa",
        "studio",
        "bedroom",
        "rent",
        "buy",
        "purchase",
        "listing",
        "bayut",
        "dubizzle",
        "jumeirah",
        "marina",
        "downtown",
        "budget",
        "price",
    ),
}


def create_user_audio_mute_processor(name: str, recorder: CallRecorder):
    """Drop user audio headed to a native realtime model while bot audio is playing."""
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    muted_frame_types = {
        "InputAudioRawFrame",
        "UserAudioRawFrame",
        "InterruptionFrame",
        "UserStartedSpeakingFrame",
        "UserStoppedSpeakingFrame",
        "VADUserStartedSpeakingFrame",
        "VADUserStoppedSpeakingFrame",
        "InterimTranscriptionFrame",
        "TranscriptionFrame",
    }

    class UserAudioMuteProcessor(FrameProcessor):
        def __init__(self) -> None:
            super().__init__(name=name)
            self._muted = False
            self._dropped_count = 0
            self._reported_drop = False

        async def process_frame(self, frame: Any, direction: FrameDirection):
            await super().process_frame(frame, direction)
            frame_type = frame.__class__.__name__

            if frame_type == "BotStartedSpeakingFrame":
                self._muted = True
                self._dropped_count = 0
                self._reported_drop = False
                recorder.emit(
                    "audio.user_input_mute_started",
                    provider="pipeline",
                    metadata={"stage": name, "frame_type": frame_type},
                )
                await self.push_frame(frame, direction)
                return

            if frame_type == "BotStoppedSpeakingFrame":
                if self._muted:
                    recorder.emit(
                        "audio.user_input_mute_stopped",
                        provider="pipeline",
                        metadata={
                            "stage": name,
                            "frame_type": frame_type,
                            "dropped_frame_count": self._dropped_count,
                        },
                    )
                self._muted = False
                self._dropped_count = 0
                self._reported_drop = False
                await self.push_frame(frame, direction)
                return

            if direction == FrameDirection.DOWNSTREAM and self._muted and frame_type in muted_frame_types:
                self._dropped_count += 1
                if not self._reported_drop:
                    recorder.emit(
                        "audio.user_input_muted_while_bot_speaking",
                        provider="pipeline",
                        metadata={"stage": name, "frame_type": frame_type},
                    )
                    self._reported_drop = True
                return

            await self.push_frame(frame, direction)

    return UserAudioMuteProcessor()


def create_instrumentation_processor(
    name: str,
    recorder: CallRecorder,
    *,
    task_ref: dict[str, Any] | None = None,
    echo_suppression_ms: int = 0,
):
    """Create a Pipecat FrameProcessor lazily so tests do not require Pipecat."""
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    class InstrumentationProcessor(FrameProcessor):
        def __init__(self) -> None:
            super().__init__(name=name)

        async def process_frame(self, frame: Any, direction: FrameDirection):
            await super().process_frame(frame, direction)
            if recorder.should_suppress_user_echo(
                frame,
                echo_suppression_ms=echo_suppression_ms,
            ):
                recorder.handle_echo_suppressed(frame, stage=name)
            recorder.handle_frame(frame, stage=name)
            if recorder.should_drop_frame(frame, stage=name):
                return
            await self.push_frame(frame, direction)

    return InstrumentationProcessor()


def create_context_limiter_processor(
    name: str,
    *,
    max_messages: int,
    recorder: CallRecorder,
):
    """Trim LLM history before provider calls to keep voice latency stable."""
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    class ContextLimiterProcessor(FrameProcessor):
        def __init__(self) -> None:
            super().__init__(name=name)

        async def process_frame(self, frame: Any, direction: FrameDirection):
            await super().process_frame(frame, direction)
            if frame.__class__.__name__ == "LLMContextFrame" and max_messages > 0:
                context = getattr(frame, "context", None)
                if context is not None:
                    messages = list(context.get_messages())
                    if len(messages) > max_messages:
                        context.set_messages(messages[-max_messages:])
                        recorder.emit(
                            "llm.context_pruned",
                            provider="pipeline",
                            metadata={
                                "original_messages": len(messages),
                                "kept_messages": max_messages,
                            },
                        )
            await self.push_frame(frame, direction)

    return ContextLimiterProcessor()


def create_alicia_conversation_mode_processor(
    name: str,
    *,
    recorder: CallRecorder,
    enabled: bool,
):
    """Inject a compact per-turn Alicia mode instruction without another LLM call."""
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    class AliciaConversationModeProcessor(FrameProcessor):
        def __init__(self) -> None:
            super().__init__(name=name)

        async def process_frame(self, frame: Any, direction: FrameDirection):
            await super().process_frame(frame, direction)
            if not enabled or frame.__class__.__name__ != "LLMContextFrame":
                await self.push_frame(frame, direction)
                return

            context = getattr(frame, "context", None)
            if (
                context is None
                or not hasattr(context, "get_messages")
                or not hasattr(context, "set_messages")
            ):
                await self.push_frame(frame, direction)
                return

            messages = list(context.get_messages())
            user_text = _last_user_message_text(messages)
            mode = classify_alicia_conversation_mode(user_text)
            instruction = MODE_INSTRUCTIONS[mode]
            cleaned_messages = [
                message
                for message in messages
                if not _message_content(message).startswith("Conversation mode:")
            ]
            context.set_messages(
                [
                    {
                        "role": "system",
                        "content": instruction,
                    },
                    *cleaned_messages,
                ]
            )
            recorder.emit(
                "conversation.mode",
                provider="pipeline",
                metadata={
                    "conversation_mode": mode,
                    "instruction_preview": instruction[:180],
                    "text_preview": user_text[:240],
                },
                once_per_turn=True,
            )
            await self.push_frame(frame, direction)

    return AliciaConversationModeProcessor()


def create_response_style_guard_processor(
    name: str,
    *,
    recorder: CallRecorder,
    enabled: bool,
):
    """Remove fast-model sales-bot recaps before text reaches TTS."""
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    class ResponseStyleGuardProcessor(FrameProcessor):
        def __init__(self) -> None:
            super().__init__(name=name)

        async def process_frame(self, frame: Any, direction: FrameDirection):
            await super().process_frame(frame, direction)
            frame_type = frame.__class__.__name__
            if not enabled or frame_type not in {"LLMTextFrame", "TextFrame"}:
                await self.push_frame(frame, direction)
                return

            original = _frame_text(frame)
            form_pattern_detected = detect_alicia_form_pattern(original)
            if form_pattern_detected:
                recorder.emit(
                    "assistant.form_pattern_detected",
                    turn_id=recorder.current_turn_id,
                    provider="pipeline",
                    metadata={
                        "frame_type": frame_type,
                        "text_preview": original[:240],
                        "form_pattern_detected": True,
                    },
                    once_per_turn=True,
                )
            rewritten = guard_alicia_response_text(original)
            if rewritten == original:
                await self.push_frame(frame, direction)
                return

            turn_id = recorder.current_turn_id
            recorder.emit(
                "assistant.style_guard_rewritten" if rewritten else "assistant.style_guard_dropped",
                turn_id=turn_id,
                provider="pipeline",
                metadata={
                    "frame_type": frame_type,
                    "original_preview": original[:240],
                    "rewritten_preview": rewritten[:240],
                    "style_guard_rewritten": bool(rewritten),
                    "form_pattern_detected": form_pattern_detected,
                },
            )
            if not rewritten:
                return
            frame.text = rewritten
            await self.push_frame(frame, direction)

    return ResponseStyleGuardProcessor()


def create_llm_error_recovery_processor(
    name: str,
    *,
    recorder: CallRecorder,
    text: str = "One sec, this model is not ready.",
):
    """Convert provider LLM failures into a short spoken fallback instead of dead air."""
    from pipecat.frames.frames import (
        LLMFullResponseEndFrame,
        LLMFullResponseStartFrame,
        LLMTextFrame,
    )
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    class LLMErrorRecoveryProcessor(FrameProcessor):
        def __init__(self) -> None:
            super().__init__(name=name)

        async def process_frame(self, frame: Any, direction: FrameDirection):
            await super().process_frame(frame, direction)
            if frame.__class__.__name__ != "ErrorFrame":
                await self.push_frame(frame, direction)
                return

            error_text = str(getattr(frame, "error", "") or "")
            provider = recorder.llm_provider
            turn_id = recorder.current_turn_id
            recorder.emit(
                "llm.error_recovered",
                turn_id=turn_id,
                provider=provider,
                metadata={
                    "llm_provider": provider,
                    "llm_model": recorder.llm_model,
                    "error_category": _provider_error_category(error_text),
                    "error_preview": _sanitize_provider_error(error_text),
                    "fallback_text": text,
                },
            )
            await self.push_frame(LLMFullResponseStartFrame(), direction)
            await self.push_frame(LLMTextFrame(text), direction)
            await self.push_frame(LLMFullResponseEndFrame(), direction)

    return LLMErrorRecoveryProcessor()


def create_flux_eager_llm_processor(
    name: str,
    *,
    context: Any,
    recorder: CallRecorder,
    enabled: bool,
):
    """Start a speculative LLM response when Flux emits EagerEndOfTurn."""
    from pipecat.frames.frames import LLMContextFrame
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    class FluxEagerLLMProcessor(FrameProcessor):
        def __init__(self) -> None:
            super().__init__(name=name)
            self._active_eager_turn_id: str | None = None
            self._cancelled_turns: set[str] = set()
            self._suppressed_final_turns: set[str] = set()

        async def process_frame(self, frame: Any, direction: FrameDirection):
            await super().process_frame(frame, direction)

            if not enabled:
                await self.push_frame(frame, direction)
                return

            frame_type = frame.__class__.__name__
            if frame_type == "InterruptionFrame":
                if self._active_eager_turn_id:
                    self._cancelled_turns.add(self._active_eager_turn_id)
                await self.push_frame(frame, direction)
                return

            if direction == FrameDirection.DOWNSTREAM and self._is_flux_eager_frame(frame):
                transcript = _frame_text(frame)
                turn_id = recorder.ensure_turn()
                recorder.mark_next_llm_start(turn_id, "eager")
                recorder.emit(
                    "transcript.ready",
                    turn_id=turn_id,
                    provider="deepgram_flux",
                    metadata={
                        "source": "eager",
                        "frame_type": frame_type,
                        "text_preview": transcript[:240],
                    },
                    once_per_turn=True,
                )
                recorder.emit(
                    "llm.eager_speculation_started",
                    turn_id=turn_id,
                    provider="pipeline",
                    metadata={"source": "flux_eager_eot"},
                    once_per_turn=True,
                )
                self._active_eager_turn_id = turn_id
                eager_context = LLMContext(
                    messages=[
                        *list(context.get_messages()),
                        {"role": "user", "content": transcript},
                    ],
                    tools=context.tools,
                    tool_choice=context.tool_choice,
                )
                context_frame = LLMContextFrame(eager_context)
                setattr(context_frame, "_verbatim_immediate_context", True)
                await self.push_frame(context_frame, direction)
                await self.push_frame(frame, direction)
                return

            if (
                direction == FrameDirection.DOWNSTREAM
                and frame_type == "LLMContextFrame"
                and self._active_eager_turn_id
                and self._active_eager_turn_id not in self._cancelled_turns
                and self._active_eager_turn_id not in self._suppressed_final_turns
            ):
                self._suppressed_final_turns.add(self._active_eager_turn_id)
                recorder.emit(
                    "llm.final_context_suppressed",
                    turn_id=self._active_eager_turn_id,
                    provider="pipeline",
                    metadata={"reason": "eager_speculation_active"},
                    once_per_turn=True,
                )
                return

            await self.push_frame(frame, direction)

        def _is_flux_eager_frame(self, frame: Any) -> bool:
            if frame.__class__.__name__ != "InterimTranscriptionFrame":
                return False
            result = getattr(frame, "result", None)
            if not isinstance(result, dict):
                return False
            return result.get("event") == "EagerEndOfTurn" and bool(_frame_text(frame))

    return FluxEagerLLMProcessor()


def create_final_transcript_eager_llm_processor(
    name: str,
    *,
    context: Any,
    recorder: CallRecorder,
    enabled: bool,
    commit_delay_ms: int = 0,
    require_complete_utterance: bool = False,
    fragment_delay_ms: int = 220,
):
    """Start the LLM on final STT transcripts, optionally after a continuation window."""
    from pipecat.frames.frames import LLMContextFrame
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    class FinalTranscriptEagerLLMProcessor(FrameProcessor):
        def __init__(self) -> None:
            super().__init__(name=name)
            self._committed_turns: set[str] = set()
            self._pending_tasks: dict[str, asyncio.Task] = {}
            self._pending_text: dict[str, str] = {}

        async def process_frame(self, frame: Any, direction: FrameDirection):
            await super().process_frame(frame, direction)

            if not enabled:
                await self.push_frame(frame, direction)
                return

            frame_type = frame.__class__.__name__
            if direction == FrameDirection.DOWNSTREAM:
                if frame_type in {
                    "UserStartedSpeakingFrame",
                    "VADUserStartedSpeakingFrame",
                    "InterimTranscriptionFrame",
                }:
                    self._cancel_pending(recorder.current_turn_id, reason="continued_speech")
                elif frame_type in {"InterruptionFrame", "CancelFrame", "EndFrame"}:
                    self._cancel_all_pending(reason=frame_type)

            if (
                direction == FrameDirection.DOWNSTREAM
                and frame_type == "TranscriptionFrame"
            ):
                transcript = _frame_text(frame)
                turn_id = recorder.ensure_turn()
                if transcript and turn_id not in self._committed_turns:
                    self._cancel_pending(turn_id, reason="updated_final_transcript", emit=False)
                    if require_complete_utterance and not looks_like_complete_utterance(transcript):
                        recorder.emit(
                            "turn.commit_gate_waiting",
                            turn_id=turn_id,
                            provider="pipeline",
                            metadata={
                                "source": "final_transcript",
                                "reason": "incomplete_utterance",
                                "frame_type": frame.__class__.__name__,
                                "text_preview": transcript[:240],
                            },
                            once_per_turn=True,
                        )
                        await self.push_frame(frame, direction)
                        return

                    delay_ms = _final_transcript_commit_delay(
                        transcript,
                        commit_delay_ms=commit_delay_ms,
                        fragment_delay_ms=fragment_delay_ms,
                    )
                    recorder.emit(
                        "turn.commit_gate_scheduled",
                        turn_id=turn_id,
                        provider="pipeline",
                        metadata={
                            "source": "final_transcript",
                            "delay_ms": delay_ms,
                            "fragment_hold": delay_ms > commit_delay_ms,
                            "frame_type": frame_type,
                            "text_preview": transcript[:240],
                        },
                        once_per_turn=True,
                    )
                    if delay_ms <= 0:
                        await self._commit_now(turn_id, transcript, direction, delay_ms)
                    else:
                        self._pending_text[turn_id] = transcript
                        self._pending_tasks[turn_id] = asyncio.create_task(
                            self._commit_after_delay(turn_id, transcript, direction, delay_ms)
                        )

            await self.push_frame(frame, direction)

        async def _commit_after_delay(
            self,
            turn_id: str,
            transcript: str,
            direction: FrameDirection,
            delay_ms: int,
        ) -> None:
            try:
                if delay_ms > 0:
                    await asyncio.sleep(delay_ms / 1000)
                if self._pending_text.get(turn_id) != transcript:
                    return
                if turn_id in self._committed_turns:
                    return
                if recorder.has_seen_event(turn_id, "llm.enqueued") or recorder.has_seen_event(
                    turn_id, "llm.request_started"
                ):
                    self._emit_commit_skipped(turn_id)
                    return
                await self._commit_now(turn_id, transcript, direction, delay_ms)
            except asyncio.CancelledError:
                return
            finally:
                task = self._pending_tasks.get(turn_id)
                if task is asyncio.current_task():
                    self._pending_tasks.pop(turn_id, None)
                    self._pending_text.pop(turn_id, None)

        def _cancel_pending(self, turn_id: str | None, *, reason: str, emit: bool = True) -> None:
            if not turn_id:
                return
            task = self._pending_tasks.pop(turn_id, None)
            self._pending_text.pop(turn_id, None)
            if task and not task.done():
                task.cancel()
                if emit:
                    recorder.emit(
                        "turn.commit_gate_cancelled",
                        turn_id=turn_id,
                        provider="pipeline",
                        metadata={"reason": reason},
                    )

        def _cancel_all_pending(self, *, reason: str) -> None:
            for turn_id in list(self._pending_tasks):
                self._cancel_pending(turn_id, reason=reason)

        async def _commit_now(
            self,
            turn_id: str,
            transcript: str,
            direction: FrameDirection,
            delay_ms: int,
        ) -> None:
            if turn_id in self._committed_turns:
                return
            if recorder.has_seen_event(turn_id, "llm.enqueued") or recorder.has_seen_event(
                turn_id, "llm.request_started"
            ):
                self._emit_commit_skipped(turn_id)
                return
            self._committed_turns.add(turn_id)
            recorder.mark_next_llm_start(turn_id, "final")
            recorder.emit(
                "turn.commit_gate_bypassed",
                turn_id=turn_id,
                provider="pipeline",
                metadata={
                    "source": "final_transcript",
                    "delay_ms": delay_ms,
                    "require_complete_utterance": require_complete_utterance,
                    "fragment_delay_ms": fragment_delay_ms,
                    "text_preview": transcript[:240],
                },
                once_per_turn=True,
            )
            recorder.emit(
                "llm.final_transcript_commit_started",
                turn_id=turn_id,
                provider="pipeline",
                metadata={"source": "final_transcript", "delay_ms": delay_ms},
                once_per_turn=True,
            )
            immediate_context = LLMContext(
                messages=[
                    *list(context.get_messages()),
                    {"role": "user", "content": transcript},
                ],
                tools=context.tools,
                tool_choice=context.tool_choice,
            )
            context_frame = LLMContextFrame(immediate_context)
            setattr(context_frame, "_verbatim_immediate_context", True)
            await self.push_frame(context_frame, direction)

        def _emit_commit_skipped(self, turn_id: str) -> None:
            recorder.emit(
                "turn.commit_gate_skipped",
                turn_id=turn_id,
                provider="pipeline",
                metadata={"reason": "normal_turn_context_already_started"},
                once_per_turn=True,
            )

    return FinalTranscriptEagerLLMProcessor()


def create_flux_final_context_gate_processor(
    name: str,
    *,
    recorder: CallRecorder,
    enabled: bool,
):
    """Drop duplicate aggregator contexts after Verbatim has already started an LLM turn."""
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    class FluxFinalContextGateProcessor(FrameProcessor):
        def __init__(self) -> None:
            super().__init__(name=name)

        async def process_frame(self, frame: Any, direction: FrameDirection):
            await super().process_frame(frame, direction)
            if getattr(frame, "_verbatim_immediate_context", False):
                await self.push_frame(frame, direction)
                return

            turn_id = recorder.current_turn_id
            should_suppress = (
                enabled
                and direction == FrameDirection.DOWNSTREAM
                and frame.__class__.__name__ == "LLMContextFrame"
                and turn_id is not None
                and (
                    recorder.has_seen_event(turn_id, "llm.eager_speculation_started")
                    or recorder.has_seen_event(turn_id, "llm.final_transcript_commit_started")
                )
                and not recorder.has_seen_event(turn_id, "turn.eager_cancelled")
                and not recorder.has_seen_event(turn_id, "llm.final_context_suppressed")
            )
            if should_suppress:
                recorder.emit(
                    "llm.final_context_suppressed",
                    turn_id=turn_id,
                    provider="pipeline",
                    metadata={"reason": "eager_speculation_active"},
                    once_per_turn=True,
                )
                return
            await self.push_frame(frame, direction)

    return FluxFinalContextGateProcessor()


def create_fast_ack_processor(
    name: str,
    *,
    recorder: CallRecorder,
    enabled: bool,
    timeout_ms: int,
    text: str,
):
    """Emit a short deterministic acknowledgement if the LLM has no speakable phrase quickly."""
    from pipecat.frames.frames import TTSSpeakFrame
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    class FastAckProcessor(FrameProcessor):
        def __init__(self) -> None:
            super().__init__(name=name)
            self._active_turn_id: str | None = None
            self._seen_speakable = False
            self._task: asyncio.Task | None = None
            self._buffer = ""

        async def process_frame(self, frame: Any, direction: FrameDirection):
            await super().process_frame(frame, direction)

            if not enabled:
                await self.push_frame(frame, direction)
                return

            frame_type = frame.__class__.__name__
            if frame_type == "LLMFullResponseStartFrame":
                self._active_turn_id = recorder.current_turn_id or recorder.ensure_turn()
                self._seen_speakable = False
                self._buffer = ""
                self._cancel_timer()
                self._task = asyncio.create_task(self._ack_after_timeout(self._active_turn_id))
                await self.push_frame(frame, direction)
                return

            if frame_type in {"LLMTextFrame", "TextFrame"} and self._active_turn_id:
                self._buffer += _frame_text(frame)
                words = WORD_RE.findall(self._buffer)
                if len(words) >= 3 or any(mark in self._buffer for mark in ".!?"):
                    self._seen_speakable = True
                    self._cancel_timer()
                await self.push_frame(frame, direction)
                return

            if frame_type in {"LLMFullResponseEndFrame", "InterruptionFrame", "EndFrame"}:
                self._cancel_timer()
                self._active_turn_id = None
                self._seen_speakable = False
                self._buffer = ""

            await self.push_frame(frame, direction)

        async def _ack_after_timeout(self, turn_id: str) -> None:
            await asyncio.sleep(max(0, timeout_ms) / 1000)
            if self._active_turn_id != turn_id or self._seen_speakable:
                return
            recorder.emit(
                "fast_ack.used",
                turn_id=turn_id,
                provider="pipeline",
                metadata={
                    "timeout_ms": timeout_ms,
                    "text_preview": text[:120],
                    "fast_ack_used": True,
                },
                once_per_turn=True,
            )
            await self.push_frame(TTSSpeakFrame(text, append_to_context=False))

        def _cancel_timer(self) -> None:
            if self._task and not self._task.done():
                self._task.cancel()
            self._task = None

    return FastAckProcessor()


def _frame_text(frame: Any) -> str:
    for attr in ("text", "transcript", "content"):
        value = getattr(frame, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _message_content(message: Any) -> str:
    if isinstance(message, dict):
        value = message.get("content")
    else:
        value = getattr(message, "content", None)
    return value.strip() if isinstance(value, str) else ""


def _message_role(message: Any) -> str:
    if isinstance(message, dict):
        value = message.get("role")
    else:
        value = getattr(message, "role", None)
    return str(value or "").lower()


def _last_user_message_text(messages: list[Any]) -> str:
    for message in reversed(messages):
        if _message_role(message) == "user":
            return _message_content(message)
    return _message_content(messages[-1]) if messages else ""


def classify_alicia_conversation_mode(text: str) -> str:
    lowered = f" {text.lower().strip()} "
    if not lowered.strip():
        return "unknown"
    for mode in (
        "stop_or_correction",
        "human_handoff",
        "repeat",
        "goodbye",
        "appointment_booking",
        "capability_explanation",
        "social",
        "property_interest",
    ):
        if any(keyword in lowered for keyword in MODE_KEYWORDS[mode]):
            return mode
    return "unknown"


def looks_like_complete_utterance(text: str) -> bool:
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return False
    lowered = cleaned.lower().strip(" .!?")
    if lowered in SHORT_COMPLETE_UTTERANCES:
        return True
    words = [word.lower() for word in WORD_RE.findall(cleaned)]
    if not words:
        return False
    if words[-1] in DANGLING_FINAL_WORDS:
        return False
    return cleaned.rstrip("\"')]").endswith((".", "?", "!"))


def looks_like_fragment_utterance(text: str) -> bool:
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return False
    if cleaned.rstrip().endswith((",", ";", ":")):
        return True
    words = [word.lower() for word in WORD_RE.findall(cleaned)]
    if not words:
        return False
    if len(words) <= 1 and words[0] not in SHORT_COMPLETE_UTTERANCES:
        return True
    return words[-1] in FRAGMENT_FINAL_WORDS


def _final_transcript_commit_delay(
    text: str,
    *,
    commit_delay_ms: int,
    fragment_delay_ms: int,
) -> int:
    if _is_short_complete_utterance(text):
        return 0
    if looks_like_fragment_utterance(text):
        return max(0, fragment_delay_ms)
    return max(0, commit_delay_ms)


def _is_short_complete_utterance(text: str) -> bool:
    cleaned = " ".join(text.strip().split())
    lowered = cleaned.lower().strip(" .!?")
    return lowered in SHORT_COMPLETE_UTTERANCES


def guard_alicia_response_text(text: str) -> str:
    original = text
    cleaned = _clean_response_spacing(text)
    if not cleaned:
        return ""

    changed = False
    for pattern in (PERSONAL_ANECDOTE_RE, MARKET_CLICHE_RE):
        updated = pattern.sub("", cleaned)
        if updated != cleaned:
            changed = True
        cleaned = _clean_response_spacing(updated)

    previous = None
    while previous != cleaned:
        previous = cleaned
        for pattern in (
            RECAP_COMMA_RE,
            RECAP_SENTENCE_RE,
            BUDGET_PRAISE_RE,
            OPTION_PRAISE_RE,
            DUBAI_FILLER_RE,
            PERSONAL_ANECDOTE_RE,
            MARKET_CLICHE_RE,
        ):
            updated = pattern.sub("", cleaned, count=1)
            if updated != cleaned:
                changed = True
            cleaned = updated
        cleaned = _clean_response_spacing(cleaned)

    updated = re.sub(r"\s+in\s+Dubai\b", "", cleaned, flags=re.IGNORECASE)
    if updated != cleaned:
        changed = True
    cleaned = updated
    updated = re.sub(r"\b(?:the\s+)?property\s+market\b", "market", cleaned, flags=re.IGNORECASE)
    if updated != cleaned:
        changed = True
    cleaned = updated
    cleaned = _clean_response_spacing(cleaned)

    for pattern, replacement in GENERIC_QUESTION_REPLACEMENTS:
        if pattern.fullmatch(cleaned.rstrip()):
            return replacement
        updated = pattern.sub(replacement, cleaned)
        if updated != cleaned:
            changed = True
        cleaned = updated

    cleaned = _clean_response_spacing(cleaned)
    if not changed:
        return original
    if not cleaned:
        return ""
    return cleaned[0].upper() + cleaned[1:] if cleaned[0].islower() else cleaned


def detect_alicia_form_pattern(text: str) -> bool:
    cleaned = _clean_response_spacing(text)
    if not cleaned:
        return False
    if any(
        pattern.search(cleaned)
        for pattern in (
            RECAP_COMMA_RE,
            RECAP_SENTENCE_RE,
            BUDGET_PRAISE_RE,
            OPTION_PRAISE_RE,
            DUBAI_FILLER_RE,
            PERSONAL_ANECDOTE_RE,
            MARKET_CLICHE_RE,
        )
    ):
        return True
    return any(pattern.search(cleaned) for pattern, _replacement in GENERIC_QUESTION_REPLACEMENTS)


def _clean_response_spacing(text: str) -> str:
    text = " ".join(text.strip().split())
    text = re.sub(r"\s+([,.?!])", r"\1", text)
    text = re.sub(r"([?!]){2,}", r"\1", text)
    return text.strip(" ,")


def _provider_error_category(error_text: str) -> str:
    lowered = error_text.lower()
    if "credit" in lowered or "license" in lowered or "billing" in lowered:
        return "provider_billing_or_access"
    if "403" in lowered or "permission" in lowered or "unauthorized" in lowered:
        return "provider_permission"
    if "rate limit" in lowered or "429" in lowered:
        return "provider_rate_limit"
    if "timeout" in lowered:
        return "provider_timeout"
    return "provider_error"


def _sanitize_provider_error(error_text: str) -> str:
    sanitized = re.sub(r"https?://\S+", "[url]", error_text)
    sanitized = re.sub(r"sk-[A-Za-z0-9_-]+", "[redacted]", sanitized)
    sanitized = re.sub(r"team/[A-Za-z0-9_-]+", "team/[redacted]", sanitized)
    return sanitized[:240]
