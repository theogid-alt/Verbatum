from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from math import ceil
from statistics import mean
from typing import Any, Iterable


LATENCY_PAIRS: dict[str, tuple[str, str]] = {
    "turn_detection_latency_ms": ("user.speech_stopped", "turn.user_committed"),
    "stt_first_interim_latency_ms": ("user.speech_started", "stt.first_interim"),
    "stt_eager_eot_latency_ms": ("user.speech_stopped", "stt.eager_end_of_turn"),
    "stt_final_eot_latency_ms": ("user.speech_stopped", "stt.utterance_end"),
    "eager_to_final_gap_ms": ("stt.eager_end_of_turn", "stt.utterance_end"),
    "stt_final_latency_ms": ("user.speech_stopped", "stt.final_transcript"),
    "transcript_to_llm_enqueue_ms": ("stt.final_transcript", "llm.enqueued"),
    "transcript_ready_to_llm_enqueue_ms": ("transcript.ready", "llm.enqueued"),
    "llm_queue_latency_ms": ("llm.enqueued", "llm.request_started"),
    "llm_queue_ms": ("llm.enqueued", "llm.request_started"),
    "llm_provider_first_chunk_ms": ("llm.request_started", "llm.provider_first_chunk"),
    "llm_provider_ttfb_ms": ("llm.request_started", "llm.first_raw_token"),
    "provider_ttft_ms": ("llm.request_started", "llm.first_raw_token"),
    "llm_ttft_total_ms": ("transcript.ready", "llm.first_text_frame_emitted"),
    "first_token_to_3_words_ms": ("llm.first_raw_token", "llm.time_to_3_words"),
    "first_token_to_6_words_ms": ("llm.first_raw_token", "llm.time_to_6_words"),
    "first_token_to_speakable_phrase_ms": (
        "llm.first_raw_token",
        "llm.first_speakable_phrase",
    ),
    "first_token_to_text_frame_ms": ("llm.first_raw_token", "llm.first_text_frame_emitted"),
    "text_frame_to_tts_input_ms": ("llm.first_text_frame_emitted", "tts.first_text_received"),
    "first_speakable_phrase_to_tts_input_ms": (
        "llm.first_speakable_phrase",
        "tts.first_text_received",
    ),
    "speakable_phrase_to_tts_audio_ms": (
        "llm.first_speakable_phrase",
        "tts.first_audio_chunk",
    ),
    "llm_first_sentence_ms": ("llm.request_started", "llm.first_sentence"),
    "llm_first_text_to_tts_ms": ("transcript.ready", "tts.first_text_received"),
    "first_text_to_tts_latency_ms": ("transcript.ready", "tts.first_text_received"),
    "tts_ttfb_ms": ("tts.first_text_received", "tts.first_audio_chunk"),
    "playback_latency_ms": ("tts.first_audio_chunk", "assistant.playback_started"),
    "perceived_response_latency_ms": ("user.speech_stopped", "assistant.playback_started"),
    "perceived_latency_ms": ("user.speech_stopped", "assistant.playback_started"),
    "transcript_ready_to_playback_ms": ("transcript.ready", "assistant.playback_started"),
    "full_turn_duration_ms": ("user.speech_stopped", "assistant.speech_completed"),
}

TIMESTAMP_FIELDS: dict[str, str] = {
    "user_speech_started_at": "user.speech_started",
    "user_speech_stopped_at": "user.speech_stopped",
    "vad_user_speech_started_at": "vad.user_speech_started",
    "vad_user_speech_stopped_at": "vad.user_speech_stopped",
    "stt_first_interim_at": "stt.first_interim",
    "stt_eager_eot_at": "stt.eager_end_of_turn",
    "stt_turn_resumed_at": "stt.turn_resumed",
    "stt_final_eot_at": "stt.utterance_end",
    "stt_final_at": "stt.final_transcript",
    "stt_final_transcript_at": "stt.final_transcript",
    "transcript_ready_at": "transcript.ready",
    "llm_enqueued_at": "llm.enqueued",
    "llm_request_started_at": "llm.request_started",
    "llm_started_at": "llm.request_started",
    "provider_first_chunk_at": "llm.provider_first_chunk",
    "llm_first_raw_token_at": "llm.first_raw_token",
    "llm_first_token_at": "llm.first_token",
    "llm_time_to_3_words_at": "llm.time_to_3_words",
    "llm_time_to_6_words_at": "llm.time_to_6_words",
    "llm_first_punctuation_at": "llm.first_punctuation",
    "llm_first_speakable_phrase_at": "llm.first_speakable_phrase",
    "llm_first_text_frame_emitted_at": "llm.first_text_frame_emitted",
    "llm_text_frame_emitted_at": "llm.text_frame_emitted",
    "llm_first_sentence_at": "llm.first_sentence",
    "first_text_sent_to_tts_at": "tts.first_text_sent",
    "first_text_to_tts_at": "tts.first_text_sent",
    "first_speakable_phrase_sent_to_tts_at": "tts.first_speakable_phrase_sent",
    "llm_done_at": "llm.completed",
    "tts_first_text_received_at": "tts.first_text_received",
    "tts_text_received_at": "tts.text_received",
    "tts_request_started_at": "tts.request_started",
    "tts_first_audio_at": "tts.first_audio_chunk",
    "assistant_playback_started_at": "assistant.playback_started",
    "assistant_speech_completed_at": "assistant.speech_completed",
}

BOTTLENECK_METRICS: dict[str, str] = {
    "turn_detection_latency_ms": "turn_detection",
    "stt_final_latency_ms": "stt_final",
    "stt_final_eot_latency_ms": "stt_final",
    "transcript_to_llm_enqueue_ms": "transcript_to_llm_enqueue",
    "transcript_ready_to_llm_enqueue_ms": "transcript_ready_to_llm_enqueue",
    "llm_queue_latency_ms": "llm_queue",
    "llm_queue_ms": "llm_queue",
    "llm_provider_first_chunk_ms": "llm_provider_ttft",
    "llm_provider_ttfb_ms": "llm_provider_ttft",
    "provider_ttft_ms": "llm_provider_ttft",
    "max_inter_token_gap_ms": "llm_stream_gap",
    "llm_stream_gap_ms": "llm_stream_gap",
    "first_token_to_3_words_ms": "llm_stream_gap",
    "first_token_to_6_words_ms": "llm_stream_gap",
    "first_token_to_speakable_phrase_ms": "first_speakable_phrase",
    "first_token_to_text_frame_ms": "first_speakable_phrase",
    "text_frame_to_tts_input_ms": "text_frame_to_tts_input",
    "first_speakable_phrase_to_tts_input_ms": "text_frame_to_tts_input",
    "llm_first_text_to_tts_ms": "text_frame_to_tts_input",
    "first_text_to_tts_latency_ms": "text_frame_to_tts_input",
    "tts_ttfb_ms": "tts_ttfb",
    "speakable_phrase_to_tts_audio_ms": "tts_ttfb",
    "playback_latency_ms": "playback_delay",
    "ultravox_response_latency_ms": "ultravox_response",
    "hume_first_audio_output_ms": "hume_provider",
    "hume_first_audio_playing_ms": "hume_first_playback",
    "hume_audio_output_to_playback_ms": "playback_delay",
}


@dataclass(frozen=True)
class TurnSummary:
    call_id: str
    turn_id: str
    latency: dict[str, float | None]
    timestamps: dict[str, float | None]
    outcome: str
    errors: list[dict[str, Any]]
    slowest_stage: str | None
    dominant_bottleneck: str
    llm_started_on: str | None
    llm_started_reason: str | None
    llm_provider: str | None
    llm_model: str | None
    turn_resumed_count: int
    eager_cancel_count: int
    active_llm_cancelled: bool
    barge_in_before_audio: bool
    stale_llm_completed: bool
    phantom_turn_prevented: bool
    tool_call: bool
    conversation_mode: str | None
    form_pattern_detected: bool
    style_guard_rewritten: bool
    premature_assistant_start: bool
    user_utterance_split: bool
    user_resumed_within_800ms_after_assistant_start: bool
    valid_barge_in: bool
    false_barge_in: bool
    voice_cutout_suspected: bool
    assistant_speech_cancelled_reason: str | None


def percentile(values: Iterable[float], p: int | float) -> float | None:
    ordered = sorted(v for v in values if v is not None)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    rank = ceil((float(p) / 100.0) * len(ordered)) - 1
    rank = min(max(rank, 0), len(ordered) - 1)
    return ordered[rank]


def _event_timestamp(event: dict[str, Any]) -> float | None:
    value = event.get("timestamp_monotonic_ms")
    return float(value) if value is not None else None


def _first_timestamps(events: list[dict[str, Any]]) -> dict[str, float]:
    timestamps: dict[str, float] = {}
    for event in sorted(events, key=lambda item: item.get("timestamp_monotonic_ms") or 0):
        event_name = event.get("event_name")
        timestamp = _event_timestamp(event)
        if event_name and timestamp is not None and event_name not in timestamps:
            timestamps[event_name] = timestamp
    return timestamps


def _timestamps_for(events: list[dict[str, Any]], event_name: str) -> list[float]:
    return [
        timestamp
        for event in sorted(events, key=lambda item: item.get("timestamp_monotonic_ms") or 0)
        if event.get("event_name") == event_name
        and (timestamp := _event_timestamp(event)) is not None
    ]


def _metric_observed_ms(
    events: list[dict[str, Any]],
    *,
    provider: str,
    metric_type: str,
) -> float | None:
    for event in sorted(events, key=lambda item: item.get("timestamp_monotonic_ms") or 0):
        if event.get("event_name") != "metrics.observed":
            continue
        if str(event.get("provider") or "").lower() != provider:
            continue
        metadata = event.get("metadata") or {}
        if metadata.get("metric_type") != metric_type:
            continue
        try:
            value_ms = float(metadata.get("value")) * 1000.0
        except (TypeError, ValueError):
            continue
        if value_ms <= 0:
            continue
        return round(value_ms, 3)
    return None


def _duration_ms(start: float | None, end: float | None) -> float | None:
    if start is None or end is None or end < start:
        return None
    return round(end - start, 3)


def compute_turn_latency(events: list[dict[str, Any]]) -> dict[str, float | None]:
    timestamps = _first_timestamps(events)
    latency: dict[str, float | None] = {}
    for metric_name, (start_event, end_event) in LATENCY_PAIRS.items():
        start = timestamps.get(start_event)
        end = timestamps.get(end_event)
        latency[metric_name] = _duration_ms(start, end)
    latency["llm_ttfb_ms"] = latency.get("llm_provider_ttfb_ms")

    if latency["stt_final_eot_latency_ms"] is None:
        latency["stt_final_eot_latency_ms"] = latency["stt_final_latency_ms"]

    tts_start = timestamps.get("tts.request_started")
    if tts_start is not None:
        text_ready = timestamps.get("llm.first_sentence") or timestamps.get("llm.first_text_chunk")
        latency["tts_queue_latency_ms"] = _duration_ms(text_ready, tts_start)
    else:
        latency["tts_queue_latency_ms"] = None

    if latency["llm_ttfb_ms"] is None:
        latency["llm_ttfb_ms"] = latency.get("llm_provider_ttfb_ms")
    if latency.get("llm_provider_ttfb_ms") is None:
        llm_start = timestamps.get("llm.request_started")
        first_text = (
            timestamps.get("llm.first_raw_token")
            or timestamps.get("llm.provider_first_chunk")
            or timestamps.get("llm.first_token")
            or timestamps.get("llm.first_text_chunk")
        )
        latency["llm_provider_ttfb_ms"] = _duration_ms(llm_start, first_text)
        latency["llm_ttfb_ms"] = latency["llm_provider_ttfb_ms"]
        latency["provider_ttft_ms"] = latency["llm_provider_ttfb_ms"]
    if latency.get("llm_provider_first_chunk_ms") is None:
        latency["llm_provider_first_chunk_ms"] = latency.get("llm_provider_ttfb_ms")
    if latency.get("llm_ttft_total_ms") is None:
        transcript_ready = timestamps.get("transcript.ready") or timestamps.get("turn.user_committed")
        first_text = (
            timestamps.get("llm.first_text_frame_emitted")
            or timestamps.get("llm.first_token")
            or timestamps.get("llm.first_text_chunk")
        )
        latency["llm_ttft_total_ms"] = _duration_ms(transcript_ready, first_text)
    if latency.get("llm_first_text_to_tts_ms") is None:
        transcript_ready = timestamps.get("transcript.ready") or timestamps.get("turn.user_committed")
        text_to_tts = timestamps.get("tts.first_text_received") or timestamps.get("tts.first_text_sent")
        latency["llm_first_text_to_tts_ms"] = _duration_ms(transcript_ready, text_to_tts)
        latency["first_text_to_tts_latency_ms"] = latency["llm_first_text_to_tts_ms"]
    if latency.get("tts_ttfb_ms") is None:
        tts_input = timestamps.get("tts.first_text_received") or timestamps.get("tts.request_started")
        latency["tts_ttfb_ms"] = _duration_ms(tts_input, timestamps.get("tts.first_audio_chunk"))
    raw_token_times = _timestamps_for(events, "llm.raw_token")
    raw_token_gaps = [
        round(end - start, 3)
        for start, end in zip(raw_token_times, raw_token_times[1:])
        if end >= start
    ]
    latency["max_inter_token_gap_ms"] = max(raw_token_gaps) if raw_token_gaps else None
    latency["llm_stream_gap_ms"] = (
        latency.get("first_token_to_3_words_ms") or latency["max_inter_token_gap_ms"]
    )
    latency["ultravox_processing_latency_ms"] = _metric_observed_ms(
        events,
        provider="ultravox",
        metric_type="ProcessingMetricsData",
    )
    return latency


def turn_timestamps(events: list[dict[str, Any]]) -> dict[str, float | None]:
    timestamps = _first_timestamps(events)
    return {
        field_name: timestamps.get(event_name)
        for field_name, event_name in TIMESTAMP_FIELDS.items()
    }


def _turn_outcome(events: list[dict[str, Any]]) -> str:
    names = {event.get("event_name") for event in events}
    if "turn.failed" in names:
        return "failed"
    if "turn.interrupted" in names or "assistant.interrupted" in names:
        return "interrupted"
    if "turn.completed" in names:
        return "success"
    return "unknown"


def _errors(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "event_name": event.get("event_name"),
            "provider": event.get("provider"),
            "metadata": event.get("metadata") or {},
        }
        for event in events
        if str(event.get("event_name", "")).endswith((".error", ".timeout"))
    ]


def slowest_available_stage(latency: dict[str, float | None]) -> str | None:
    candidates = {
        key: value
        for key, value in latency.items()
        if key in BOTTLENECK_METRICS and value is not None
    }
    if not candidates:
        return None
    return max(candidates, key=lambda key: candidates[key] or 0)


def dominant_bottleneck(latency: dict[str, float | None], events: list[dict[str, Any]] | None = None) -> str:
    names = {event.get("event_name") for event in events or []}
    if "llm.stale_completed" in names or (
        "llm.active_cancelled" in names and "barge_in.before_audio" in names
    ):
        return "interruption_recovery"
    if any(str(name).startswith("tool.") for name in names):
        return "tool_call"
    slowest_stage = slowest_available_stage(latency)
    if slowest_stage is None:
        return "unknown"
    return BOTTLENECK_METRICS.get(slowest_stage, "unknown")


def llm_started_on(events: list[dict[str, Any]]) -> str | None:
    timestamps = _first_timestamps(events)
    llm_start = timestamps.get("llm.request_started")
    if llm_start is None:
        return None

    eager = timestamps.get("stt.eager_end_of_turn")
    final_gate = (
        timestamps.get("turn.user_committed")
        or timestamps.get("stt.final_transcript")
        or timestamps.get("stt.utterance_end")
    )
    if eager is not None and (final_gate is None or llm_start < final_gate):
        return "eager"
    if final_gate is not None and llm_start >= final_gate:
        return "final"
    return "unknown"


def llm_started_reason(events: list[dict[str, Any]]) -> str | None:
    for event in sorted(events, key=lambda item: item.get("timestamp_monotonic_ms") or 0):
        if event.get("event_name") not in {"llm.enqueued", "llm.request_started"}:
            continue
        metadata = event.get("metadata") or {}
        reason = metadata.get("llm_started_reason")
        if reason:
            return str(reason)
    return llm_started_on(events)


def llm_metadata(events: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    for event in sorted(events, key=lambda item: item.get("timestamp_monotonic_ms") or 0):
        event_name = str(event.get("event_name") or "")
        if not event_name.startswith("llm.") and event_name not in {
            "tts.first_text_sent",
            "tts.first_text_received",
        }:
            continue
        metadata = event.get("metadata") or {}
        provider = metadata.get("llm_provider") or event.get("provider")
        model = metadata.get("llm_model")
        if provider or model:
            return (
                str(provider) if provider else None,
                str(model) if model else None,
            )
    return None, None


def _turn_resumed_count(events: list[dict[str, Any]]) -> int:
    return sum(1 for event in events if event.get("event_name") == "stt.turn_resumed")


def _eager_cancel_count(events: list[dict[str, Any]]) -> int:
    return sum(1 for event in events if event.get("event_name") == "turn.eager_cancelled")


def _has_event(events: list[dict[str, Any]], event_name: str) -> bool:
    return any(event.get("event_name") == event_name for event in events)


def _has_tool_event(events: list[dict[str, Any]]) -> bool:
    return any(str(event.get("event_name") or "").startswith("tool.") for event in events)


def _first_metadata_value(events: list[dict[str, Any]], event_name: str, key: str) -> str | None:
    for event in sorted(events, key=lambda item: item.get("timestamp_monotonic_ms") or 0):
        if event.get("event_name") != event_name:
            continue
        value = (event.get("metadata") or {}).get(key)
        if value:
            return str(value)
    return None


def _session_config_metadata(events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in reversed(events):
        if event.get("event_name") == "session.configured":
            return dict(event.get("metadata") or {})
    return {}


def _ultravox_response_latency_by_turn(events: list[dict[str, Any]]) -> dict[str, float]:
    latencies: dict[str, float] = {}
    last_user_transcript_at: float | None = None
    for event in sorted(events, key=lambda item: item.get("timestamp_monotonic_ms") or 0):
        timestamp = _event_timestamp(event)
        if timestamp is None:
            continue
        event_name = event.get("event_name")
        if event_name == "ultravox.transcript.user":
            last_user_transcript_at = timestamp
            continue
        if event_name != "assistant.playback_started" or last_user_transcript_at is None:
            continue
        turn_id = event.get("turn_id")
        latency = _duration_ms(last_user_transcript_at, timestamp)
        last_user_transcript_at = None
        if not turn_id or latency is None:
            continue
        latencies[str(turn_id)] = latency
    return latencies


def _metadata_text(event: dict[str, Any]) -> str:
    metadata = event.get("metadata") or {}
    return str(
        metadata.get("transcript")
        or metadata.get("text_preview")
        or metadata.get("text")
        or ""
    ).strip()


def _dedupe_hume_message_events(
    events: list[dict[str, Any]],
    event_name: str,
    *,
    window_ms: float = 1800,
) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    last_text = ""
    last_timestamp: float | None = None
    for event in sorted(events, key=lambda item: item.get("timestamp_monotonic_ms") or 0):
        if event.get("event_name") != event_name:
            continue
        timestamp = _event_timestamp(event)
        text = _metadata_text(event)
        if (
            text
            and text == last_text
            and timestamp is not None
            and last_timestamp is not None
            and timestamp - last_timestamp <= window_ms
        ):
            continue
        deduped.append(event)
        last_text = text
        last_timestamp = timestamp
    return deduped


def _event_between(
    events: list[dict[str, Any]],
    event_name: str,
    start: float,
    end: float | None,
) -> dict[str, Any] | None:
    for event in sorted(events, key=lambda item: item.get("timestamp_monotonic_ms") or 0):
        timestamp = _event_timestamp(event)
        if timestamp is None or timestamp < start:
            continue
        if end is not None and timestamp >= end:
            continue
        if event.get("event_name") == event_name:
            return event
    return None


def _hume_evi_turn_summaries(events: list[dict[str, Any]]) -> list[TurnSummary]:
    user_messages = _dedupe_hume_message_events(events, "hume.client.user_message")
    summaries: list[TurnSummary] = []
    for index, user_event in enumerate(user_messages, start=1):
        user_timestamp = _event_timestamp(user_event)
        if user_timestamp is None:
            continue
        next_user_timestamp = (
            _event_timestamp(user_messages[index])
            if index < len(user_messages)
            else None
        )
        first_audio_output = _event_between(
            events,
            "hume.client.first_audio_output",
            user_timestamp,
            next_user_timestamp,
        ) or _event_between(
            events,
            "hume.client.audio_output",
            user_timestamp,
            next_user_timestamp,
        )
        first_audio_playing = _event_between(
            events,
            "hume.client.first_audio_playing",
            user_timestamp,
            next_user_timestamp,
        ) or _event_between(
            events,
            "hume.client.audio_playing",
            user_timestamp,
            next_user_timestamp,
        )
        assistant_message = _event_between(
            events,
            "hume.client.assistant_message",
            user_timestamp,
            next_user_timestamp,
        )
        output_timestamp = _event_timestamp(first_audio_output) if first_audio_output else None
        playing_timestamp = _event_timestamp(first_audio_playing) if first_audio_playing else None
        latency = {
            "hume_first_audio_output_ms": _duration_ms(user_timestamp, output_timestamp),
            "hume_first_audio_playing_ms": _duration_ms(user_timestamp, playing_timestamp),
            "hume_audio_output_to_playback_ms": _duration_ms(output_timestamp, playing_timestamp),
            "transcript_ready_to_playback_ms": _duration_ms(user_timestamp, playing_timestamp),
            "perceived_response_latency_ms": _duration_ms(user_timestamp, playing_timestamp),
        }
        slowest_stage = slowest_available_stage(latency)
        turn_events = [
            event
            for event in events
            if (timestamp := _event_timestamp(event)) is not None
            and timestamp >= user_timestamp
            and (next_user_timestamp is None or timestamp < next_user_timestamp)
        ]
        summaries.append(
            TurnSummary(
                call_id=str(user_event.get("call_id", "")),
                turn_id=f"turn_{index:04d}",
                latency=latency,
                timestamps={
                    "hume_user_message_at": user_timestamp,
                    "hume_first_audio_output_at": output_timestamp,
                    "hume_first_audio_playing_at": playing_timestamp,
                    "hume_assistant_message_at": _event_timestamp(assistant_message)
                    if assistant_message
                    else None,
                },
                outcome="success" if first_audio_playing or assistant_message else "unknown",
                errors=_errors(turn_events),
                slowest_stage=slowest_stage,
                dominant_bottleneck=dominant_bottleneck(latency, turn_events),
                llm_started_on="hume_evi",
                llm_started_reason="hume_evi",
                llm_provider="hume_evi",
                llm_model="hume-evi",
                turn_resumed_count=0,
                eager_cancel_count=0,
                active_llm_cancelled=False,
                barge_in_before_audio=False,
                stale_llm_completed=False,
                phantom_turn_prevented=False,
                tool_call=False,
                conversation_mode=None,
                form_pattern_detected=False,
                style_guard_rewritten=False,
                premature_assistant_start=False,
                user_utterance_split=False,
                user_resumed_within_800ms_after_assistant_start=False,
                valid_barge_in=_has_event(turn_events, "hume.client.user_interruption"),
                false_barge_in=False,
                voice_cutout_suspected=_has_event(turn_events, "hume.client.audio_playback_error"),
                assistant_speech_cancelled_reason=None,
            )
        )
    return summaries


def summarize_turn_events(events: list[dict[str, Any]]) -> TurnSummary:
    call_id = str(events[0].get("call_id", "")) if events else ""
    turn_id = str(events[0].get("turn_id", "")) if events else ""
    latency = compute_turn_latency(events)
    slowest_stage = slowest_available_stage(latency)
    provider, model = llm_metadata(events)
    return TurnSummary(
        call_id=call_id,
        turn_id=turn_id,
        latency=latency,
        timestamps=turn_timestamps(events),
        outcome=_turn_outcome(events),
        errors=_errors(events),
        slowest_stage=slowest_stage,
        dominant_bottleneck=dominant_bottleneck(latency, events),
        llm_started_on=llm_started_on(events),
        llm_started_reason=llm_started_reason(events),
        llm_provider=provider,
        llm_model=model,
        turn_resumed_count=_turn_resumed_count(events),
        eager_cancel_count=_eager_cancel_count(events),
        active_llm_cancelled=_has_event(events, "llm.active_cancelled"),
        barge_in_before_audio=_has_event(events, "barge_in.before_audio"),
        stale_llm_completed=_has_event(events, "llm.stale_completed"),
        phantom_turn_prevented=_has_event(events, "turn.phantom_prevented"),
        tool_call=_has_tool_event(events),
        conversation_mode=_first_metadata_value(
            events,
            "conversation.mode",
            "conversation_mode",
        ),
        form_pattern_detected=_has_event(events, "assistant.form_pattern_detected"),
        style_guard_rewritten=_has_event(events, "assistant.style_guard_rewritten")
        or _has_event(events, "assistant.style_guard_dropped"),
        premature_assistant_start=_has_event(events, "turn.premature_assistant_start"),
        user_utterance_split=_has_event(events, "turn.user_utterance_split"),
        user_resumed_within_800ms_after_assistant_start=_has_event(
            events,
            "user.resumed_within_800ms_after_assistant_start",
        ),
        valid_barge_in=_has_event(events, "barge_in.valid"),
        false_barge_in=_has_event(events, "barge_in.false"),
        voice_cutout_suspected=_has_event(events, "voice.cutout_suspected"),
        assistant_speech_cancelled_reason=_first_metadata_value(
            events,
            "assistant.interrupted",
            "assistant_speech_cancelled_reason",
        ),
    )


def group_events_by_call_and_turn(
    events: Iterable[dict[str, Any]],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for event in events:
        call_id = event.get("call_id")
        turn_id = event.get("turn_id")
        if call_id and turn_id:
            grouped[str(call_id)][str(turn_id)].append(event)
    return grouped


def summarize_call_events(events: list[dict[str, Any]], call_id: str | None = None) -> dict[str, Any]:
    if call_id is not None:
        events = [event for event in events if event.get("call_id") == call_id]
    grouped = group_events_by_call_and_turn(events)
    turn_summaries: list[TurnSummary] = []
    for turns in grouped.values():
        for turn_events in turns.values():
            turn_summaries.append(summarize_turn_events(turn_events))
    session_config = _session_config_metadata(events)
    transport_provider = session_config.get("transport_provider")
    room_name = session_config.get("room_name")
    llm_provider = session_config.get("llm_provider") or next(
        (summary.llm_provider for summary in turn_summaries if summary.llm_provider),
        None,
    )
    llm_model = session_config.get("llm_model") or session_config.get("gemini_model") or next(
        (summary.llm_model for summary in turn_summaries if summary.llm_model),
        None,
    )
    is_hume_evi = str(transport_provider or llm_provider or "").lower() == "hume_evi"
    if is_hume_evi:
        turn_summaries.extend(_hume_evi_turn_summaries(events))

    perceived = [
        summary.latency.get("perceived_response_latency_ms")
        for summary in turn_summaries
        if summary.latency.get("perceived_response_latency_ms") is not None
    ]
    transcript_ready_to_playback_all = [
        summary.latency.get("transcript_ready_to_playback_ms")
        for summary in turn_summaries
        if summary.latency.get("transcript_ready_to_playback_ms") is not None
    ]
    ultravox_processing_all = [
        summary.latency.get("ultravox_processing_latency_ms")
        for summary in turn_summaries
        if summary.latency.get("ultravox_processing_latency_ms") is not None
    ]
    provider_errors = Counter(
        str(event.get("provider") or "unknown")
        for event in events
        if str(event.get("event_name", "")).endswith((".error", ".timeout"))
    )
    llm_start_counts = Counter(
        summary.llm_started_reason or summary.llm_started_on
        for summary in turn_summaries
        if summary.llm_started_reason or summary.llm_started_on
    )
    is_ultravox = str(llm_provider or "").lower() == "ultravox"
    if is_ultravox:
        response_latency_by_turn = _ultravox_response_latency_by_turn(events)
        for summary in turn_summaries:
            raw_latency = response_latency_by_turn.get(summary.turn_id)
            if raw_latency is None:
                continue
            summary.latency["ultravox_response_latency_raw_ms"] = raw_latency
            if raw_latency >= 100:
                summary.latency["ultravox_response_latency_ms"] = raw_latency
            else:
                summary.latency["ultravox_response_latency_ms"] = None
    ultravox_response_all = [
        summary.latency.get("ultravox_response_latency_ms")
        for summary in turn_summaries
        if summary.latency.get("ultravox_response_latency_ms") is not None
    ]
    if is_ultravox and ultravox_response_all:
        perceived_display = ultravox_response_all
        perceived_latency_source = "ultravox_user_final_to_playback"
        critical_turns = [
            summary
            for summary in turn_summaries
            if summary.latency.get("ultravox_response_latency_ms") is not None
        ]
    elif is_ultravox and ultravox_processing_all:
        perceived_display = ultravox_processing_all
        perceived_latency_source = "ultravox_processing_full_response"
        critical_turns = [
            summary
            for summary in turn_summaries
            if summary.latency.get("ultravox_processing_latency_ms") is not None
        ]
    elif is_hume_evi and transcript_ready_to_playback_all:
        perceived_display = transcript_ready_to_playback_all
        perceived_latency_source = "hume_user_message_to_first_audio_playing"
        critical_turns = [
            summary
            for summary in turn_summaries
            if summary.latency.get("transcript_ready_to_playback_ms") is not None
        ]
    elif transcript_ready_to_playback_all:
        perceived_display = transcript_ready_to_playback_all
        perceived_latency_source = "transcript_ready_to_playback"
        critical_turns = [
            summary
            for summary in turn_summaries
            if summary.latency.get("transcript_ready_to_playback_ms") is not None
        ]
    elif perceived:
        perceived_display = perceived
        perceived_latency_source = "user_speech_stopped"
        critical_turns = [
            summary
            for summary in turn_summaries
            if summary.latency.get("perceived_response_latency_ms") is not None
        ]
    else:
        perceived_display = []
        perceived_latency_source = None
        critical_turns = turn_summaries

    def avg(metric_name: str, *, scoped: bool = True) -> float | None:
        summaries = critical_turns if scoped else turn_summaries
        values = [
            summary.latency.get(metric_name)
            for summary in summaries
            if summary.latency.get(metric_name) is not None
        ]
        return round(mean(values), 3) if values else None

    def metric_values(metric_name: str, *, scoped: bool = True) -> list[float]:
        summaries = critical_turns if scoped else turn_summaries
        return [
            value
            for summary in summaries
            if (value := summary.latency.get(metric_name)) is not None
        ]

    def values_for(summaries: list[TurnSummary], metric_name: str) -> list[float]:
        return [
            value
            for summary in summaries
            if (value := summary.latency.get(metric_name)) is not None
        ]

    def scoped_p95(summaries: list[TurnSummary], metric_name: str) -> float | None:
        return percentile(values_for(summaries, metric_name), 95)

    def is_clean(summary: TurnSummary) -> bool:
        return (
            summary.outcome == "success"
            and not summary.errors
            and not summary.active_llm_cancelled
            and not summary.barge_in_before_audio
            and not summary.stale_llm_completed
            and not summary.tool_call
        )

    def turn_number(summary: TurnSummary) -> int | None:
        try:
            return int(summary.turn_id.rsplit("_", 1)[-1])
        except (TypeError, ValueError):
            return None

    transcript_ready_to_enqueue = metric_values("transcript_ready_to_llm_enqueue_ms")
    transcript_ready_to_playback = metric_values("transcript_ready_to_playback_ms")
    ultravox_response = metric_values("ultravox_response_latency_ms")
    ultravox_processing = metric_values("ultravox_processing_latency_ms", scoped=False)
    llm_provider_ttfb = metric_values("llm_provider_ttfb_ms")
    first_token_to_3_words = metric_values("first_token_to_3_words_ms")
    first_token_to_6_words = metric_values("first_token_to_6_words_ms")
    first_token_to_speakable = metric_values("first_token_to_speakable_phrase_ms")
    speakable_to_audio = metric_values("speakable_phrase_to_tts_audio_ms")
    max_inter_token_gap = metric_values("max_inter_token_gap_ms")
    hume_first_audio_output = metric_values("hume_first_audio_output_ms")
    hume_first_audio_playing = metric_values("hume_first_audio_playing_ms")
    hume_audio_output_to_playback = metric_values("hume_audio_output_to_playback_ms")
    bottleneck_counts = Counter(summary.dominant_bottleneck for summary in turn_summaries)
    if is_ultravox and ultravox_response:
        real_latency_metric = "ultravox_response_latency_ms"
        real_p95 = percentile(ultravox_response, 95)
    elif is_ultravox and ultravox_processing:
        real_latency_metric = "ultravox_processing_latency_ms"
        real_p95 = percentile(ultravox_processing, 95)
    else:
        real_latency_metric = "transcript_ready_to_playback_ms"
        real_p95 = percentile(transcript_ready_to_playback, 95)
    if real_p95 is None:
        real_latency_metric = "perceived_response_latency_ms"
        real_p95 = percentile(perceived, 95)
    p95_turns = [
        summary
        for summary in turn_summaries
        if real_p95 is not None
        and (value := summary.latency.get(real_latency_metric)) is not None
        and value >= real_p95
    ]
    p95_bottlenecks = Counter(summary.dominant_bottleneck for summary in p95_turns)
    p95_total = sum(p95_bottlenecks.values())
    clean_turns = [summary for summary in turn_summaries if is_clean(summary)]
    interrupted_turns = [
        summary
        for summary in turn_summaries
        if summary.outcome == "interrupted" or summary.active_llm_cancelled or summary.barge_in_before_audio
    ]
    tool_turns = [summary for summary in turn_summaries if summary.tool_call]
    first_turns = [summary for summary in turn_summaries if turn_number(summary) == 1]
    later_turns = [
        summary
        for summary in turn_summaries
        if (number := turn_number(summary)) is not None and number > 1
    ]
    conversation_mode_counts = Counter(
        summary.conversation_mode or "unknown" for summary in turn_summaries
    )

    def display_latency(summary: TurnSummary) -> float | None:
        if is_ultravox:
            if ultravox_response:
                return summary.latency.get("ultravox_response_latency_ms")
            if ultravox_processing:
                return summary.latency.get("ultravox_processing_latency_ms")
        return (
            summary.latency.get("transcript_ready_to_playback_ms")
            or summary.latency.get("perceived_response_latency_ms")
        )

    clean_display_latencies = [
        value for summary in clean_turns if (value := display_latency(summary)) is not None
    ]
    all_display_latencies = [
        value for summary in turn_summaries if (value := display_latency(summary)) is not None
    ]

    return {
        "schema_version": "0.1",
        "call_id": call_id,
        "transport_provider": transport_provider,
        "room_name": room_name,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "config_snapshot": session_config,
        "total_turns": len(turn_summaries),
        "successful_turns": sum(1 for summary in turn_summaries if summary.outcome == "success"),
        "failed_turns": sum(1 for summary in turn_summaries if summary.outcome == "failed"),
        "interrupted_turns": sum(
            1 for summary in turn_summaries if summary.outcome == "interrupted"
        ),
        "avg_perceived_latency_ms": (
            round(mean(perceived_display), 3) if perceived_display else None
        ),
        "p50_perceived_latency_ms": percentile(perceived_display, 50),
        "p90_perceived_latency_ms": percentile(perceived_display, 90),
        "p95_perceived_latency_ms": percentile(perceived_display, 95),
        "max_perceived_latency_ms": max(perceived_display) if perceived_display else None,
        "real_p95_ms": percentile(all_display_latencies, 95),
        "clean_p95_ms": percentile(clean_display_latencies, 95),
        "perceived_latency_source": perceived_latency_source,
        "avg_transcript_to_llm_enqueue_ms": avg("transcript_to_llm_enqueue_ms"),
        "avg_transcript_ready_to_llm_enqueue_ms": avg("transcript_ready_to_llm_enqueue_ms"),
        "p95_transcript_ready_to_llm_enqueue_ms": percentile(transcript_ready_to_enqueue, 95),
        "max_transcript_ready_to_llm_enqueue_ms": (
            max(transcript_ready_to_enqueue) if transcript_ready_to_enqueue else None
        ),
        "avg_transcript_ready_to_playback_ms": (
            round(mean(transcript_ready_to_playback), 3)
            if transcript_ready_to_playback
            else None
        ),
        "p50_transcript_ready_to_playback_ms": percentile(transcript_ready_to_playback, 50),
        "p90_transcript_ready_to_playback_ms": percentile(transcript_ready_to_playback, 90),
        "p95_transcript_ready_to_playback_ms": percentile(transcript_ready_to_playback, 95),
        "max_transcript_ready_to_playback_ms": (
            max(transcript_ready_to_playback) if transcript_ready_to_playback else None
        ),
        "avg_ultravox_response_latency_ms": (
            round(mean(ultravox_response), 3) if ultravox_response else None
        ),
        "p50_ultravox_response_latency_ms": percentile(ultravox_response, 50),
        "p90_ultravox_response_latency_ms": percentile(ultravox_response, 90),
        "p95_ultravox_response_latency_ms": percentile(ultravox_response, 95),
        "max_ultravox_response_latency_ms": (
            max(ultravox_response) if ultravox_response else None
        ),
        "avg_ultravox_processing_latency_ms": (
            round(mean(ultravox_processing), 3) if ultravox_processing else None
        ),
        "p50_ultravox_processing_latency_ms": percentile(ultravox_processing, 50),
        "p90_ultravox_processing_latency_ms": percentile(ultravox_processing, 90),
        "p95_ultravox_processing_latency_ms": percentile(ultravox_processing, 95),
        "max_ultravox_processing_latency_ms": (
            max(ultravox_processing) if ultravox_processing else None
        ),
        "avg_hume_first_audio_output_ms": (
            round(mean(hume_first_audio_output), 3) if hume_first_audio_output else None
        ),
        "p50_hume_first_audio_output_ms": percentile(hume_first_audio_output, 50),
        "p90_hume_first_audio_output_ms": percentile(hume_first_audio_output, 90),
        "p95_hume_first_audio_output_ms": percentile(hume_first_audio_output, 95),
        "max_hume_first_audio_output_ms": (
            max(hume_first_audio_output) if hume_first_audio_output else None
        ),
        "avg_hume_first_audio_playing_ms": (
            round(mean(hume_first_audio_playing), 3) if hume_first_audio_playing else None
        ),
        "p50_hume_first_audio_playing_ms": percentile(hume_first_audio_playing, 50),
        "p90_hume_first_audio_playing_ms": percentile(hume_first_audio_playing, 90),
        "p95_hume_first_audio_playing_ms": percentile(hume_first_audio_playing, 95),
        "max_hume_first_audio_playing_ms": (
            max(hume_first_audio_playing) if hume_first_audio_playing else None
        ),
        "avg_hume_audio_output_to_playback_ms": (
            round(mean(hume_audio_output_to_playback), 3)
            if hume_audio_output_to_playback
            else None
        ),
        "p95_hume_audio_output_to_playback_ms": percentile(
            hume_audio_output_to_playback,
            95,
        ),
        "avg_llm_queue_latency_ms": avg("llm_queue_latency_ms"),
        "avg_llm_queue_ms": avg("llm_queue_ms"),
        "avg_llm_provider_first_chunk_ms": avg("llm_provider_first_chunk_ms"),
        "avg_llm_provider_ttfb_ms": avg("llm_provider_ttfb_ms"),
        "p95_llm_provider_ttfb_ms": percentile(llm_provider_ttfb, 95),
        "max_llm_provider_ttfb_ms": max(llm_provider_ttfb) if llm_provider_ttfb else None,
        "avg_provider_ttft_ms": avg("provider_ttft_ms"),
        "avg_first_token_to_3_words_ms": (
            round(mean(first_token_to_3_words), 3) if first_token_to_3_words else None
        ),
        "p95_first_token_to_3_words_ms": percentile(first_token_to_3_words, 95),
        "avg_first_token_to_6_words_ms": (
            round(mean(first_token_to_6_words), 3) if first_token_to_6_words else None
        ),
        "p95_first_token_to_6_words_ms": percentile(first_token_to_6_words, 95),
        "avg_first_token_to_speakable_phrase_ms": (
            round(mean(first_token_to_speakable), 3) if first_token_to_speakable else None
        ),
        "p95_first_token_to_speakable_phrase_ms": percentile(first_token_to_speakable, 95),
        "avg_max_inter_token_gap_ms": (
            round(mean(max_inter_token_gap), 3) if max_inter_token_gap else None
        ),
        "p95_max_inter_token_gap_ms": percentile(max_inter_token_gap, 95),
        "avg_first_token_to_text_frame_ms": avg("first_token_to_text_frame_ms"),
        "avg_text_frame_to_tts_input_ms": avg("text_frame_to_tts_input_ms"),
        "avg_first_speakable_phrase_to_tts_input_ms": avg(
            "first_speakable_phrase_to_tts_input_ms"
        ),
        "avg_speakable_phrase_to_tts_audio_ms": (
            round(mean(speakable_to_audio), 3) if speakable_to_audio else None
        ),
        "p95_speakable_phrase_to_tts_audio_ms": percentile(speakable_to_audio, 95),
        "avg_llm_ttft_total_ms": avg("llm_ttft_total_ms"),
        "avg_llm_first_text_to_tts_ms": avg("llm_first_text_to_tts_ms"),
        "avg_llm_ttfb_ms": avg("llm_provider_ttfb_ms"),
        "avg_tts_ttfb_ms": avg("tts_ttfb_ms"),
        "avg_turn_detection_latency_ms": avg("turn_detection_latency_ms"),
        "avg_stt_eager_eot_latency_ms": avg("stt_eager_eot_latency_ms"),
        "avg_stt_final_eot_latency_ms": avg("stt_final_eot_latency_ms"),
        "avg_eager_to_final_gap_ms": avg("eager_to_final_gap_ms"),
        "avg_stt_final_latency_ms": avg("stt_final_latency_ms"),
        "avg_playback_latency_ms": avg("playback_latency_ms"),
        "turn_resumed_count": sum(summary.turn_resumed_count for summary in turn_summaries),
        "eager_cancel_count": sum(summary.eager_cancel_count for summary in turn_summaries),
        "active_llm_cancelled_count": sum(1 for summary in turn_summaries if summary.active_llm_cancelled),
        "barge_in_before_audio_count": sum(1 for summary in turn_summaries if summary.barge_in_before_audio),
        "stale_llm_completed_count": sum(1 for summary in turn_summaries if summary.stale_llm_completed),
        "phantom_turn_prevented_count": sum(
            1 for summary in turn_summaries if summary.phantom_turn_prevented
        ),
        "ultravox_playback_clear_buffer_count": sum(
            1 for event in events if event.get("event_name") == "ultravox.playback_clear_buffer"
        ),
        "echo_suppressed_count": sum(
            1 for event in events if event.get("event_name") == "audio.echo_suppressed"
        ),
        "valid_barge_in_count": sum(1 for summary in turn_summaries if summary.valid_barge_in),
        "false_barge_in_count": sum(1 for summary in turn_summaries if summary.false_barge_in),
        "premature_assistant_start_count": sum(
            1 for summary in turn_summaries if summary.premature_assistant_start
        ),
        "user_utterance_split_count": sum(
            1 for summary in turn_summaries if summary.user_utterance_split
        ),
        "voice_cutout_suspected_count": sum(
            1 for summary in turn_summaries if summary.voice_cutout_suspected
        ),
        "form_pattern_failure_count": sum(
            1 for summary in turn_summaries if summary.form_pattern_detected
        ),
        "style_guard_rewrite_count": sum(
            1 for summary in turn_summaries if summary.style_guard_rewritten
        ),
        "conversation_mode_counts": dict(conversation_mode_counts),
        "llm_started_on_counts": dict(llm_start_counts),
        "error_count_by_provider": dict(provider_errors),
        "bottleneck_counts": dict(bottleneck_counts),
        "p95_bottleneck_contributors": [
            {
                "bottleneck": bottleneck,
                "turns": count,
                "percent": round((count / p95_total) * 100, 1) if p95_total else 0,
            }
            for bottleneck, count in p95_bottlenecks.most_common()
        ],
        "clean_p95_transcript_ready_to_playback_ms": scoped_p95(
            clean_turns, "transcript_ready_to_playback_ms"
        ),
        "clean_p95_perceived_latency_ms": scoped_p95(clean_turns, "perceived_response_latency_ms"),
        "clean_p95_ultravox_processing_latency_ms": scoped_p95(
            clean_turns, "ultravox_processing_latency_ms"
        ),
        "interrupted_p95_transcript_ready_to_playback_ms": scoped_p95(
            interrupted_turns, "transcript_ready_to_playback_ms"
        ),
        "tool_call_p95_transcript_ready_to_playback_ms": scoped_p95(
            tool_turns, "transcript_ready_to_playback_ms"
        ),
        "first_turn_p95_transcript_ready_to_playback_ms": scoped_p95(
            first_turns, "transcript_ready_to_playback_ms"
        ),
        "later_turn_p95_transcript_ready_to_playback_ms": scoped_p95(
            later_turns, "transcript_ready_to_playback_ms"
        ),
        "turns": [
            {
                "call_id": summary.call_id,
                "turn_id": summary.turn_id,
                "outcome": summary.outcome,
                "latency": summary.latency,
                "timestamps": summary.timestamps,
                "errors": summary.errors,
                "slowest_stage": summary.slowest_stage,
                "dominant_bottleneck": summary.dominant_bottleneck,
                "llm_started_on": summary.llm_started_on,
                "llm_started_reason": summary.llm_started_reason,
                "llm_provider": summary.llm_provider,
                "llm_model": summary.llm_model,
                "turn_resumed_count": summary.turn_resumed_count,
                "eager_cancel_count": summary.eager_cancel_count,
                "active_llm_cancelled": summary.active_llm_cancelled,
                "barge_in_before_audio": summary.barge_in_before_audio,
                "stale_llm_completed": summary.stale_llm_completed,
                "phantom_turn_prevented": summary.phantom_turn_prevented,
                "tool_call": summary.tool_call,
                "conversation_mode": summary.conversation_mode,
                "form_pattern_detected": summary.form_pattern_detected,
                "style_guard_rewritten": summary.style_guard_rewritten,
                "premature_assistant_start": summary.premature_assistant_start,
                "user_utterance_split": summary.user_utterance_split,
                "user_resumed_within_800ms_after_assistant_start": (
                    summary.user_resumed_within_800ms_after_assistant_start
                ),
                "valid_barge_in": summary.valid_barge_in,
                "false_barge_in": summary.false_barge_in,
                "voice_cutout_suspected": summary.voice_cutout_suspected,
                "assistant_speech_cancelled_reason": (
                    summary.assistant_speech_cancelled_reason
                ),
            }
            for summary in turn_summaries
        ],
    }
