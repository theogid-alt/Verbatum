from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
from typing import Any, Iterable


def summarize_call_events(events: Iterable[dict[str, Any]], *, call_id: str | None = None) -> dict[str, Any]:
    selected = [event for event in events if not call_id or event.get("call_id") == call_id]
    selected.sort(key=lambda item: item.get("timestamp_monotonic_ms") or 0)
    turns: dict[str, dict[str, Any]] = defaultdict(lambda: {"timestamps": {}, "latency": {}, "metadata": {}})
    config = _config_snapshot(selected)
    errors = 0
    for event in selected:
        name = _canonical_event_name(event.get("event_name"))
        if name == "error":
            errors += 1
        turn_id = event.get("turn_id")
        if not turn_id:
            continue
        turn = turns[turn_id]
        turn["turn_id"] = turn_id
        turn["timestamps"][name] = event.get("timestamp_monotonic_ms")
        metadata = event.get("metadata") or {}
        if name == "transcript.user":
            _set_metadata_timestamp(turn["timestamps"], "user.speech.started", metadata.get("user_speech_started_at_ms"))
            _set_metadata_timestamp(turn["timestamps"], "user.speech.stopped", metadata.get("user_speech_stopped_at_ms"))
            _set_metadata_latency(turn["latency"], "stt_processing_ms", metadata.get("stt_processing_ms"))
        if name in {"transcript.user", "transcript.assistant"} and metadata.get("text"):
            turn["metadata"][name] = metadata.get("text")

    for turn in turns.values():
        timestamps = turn["timestamps"]
        latency = turn["latency"]
        _set_delta(latency, "provider_ttft_ms", timestamps, "llm.request.started", "llm.first.token")
        _set_delta(latency, "tts_first_audio_ms", timestamps, "tts.request.started", "tts.first.audio")
        _set_delta(latency, "playback_delay_ms", timestamps, "tts.first.audio", "assistant.playback.started")
        if "stt_processing_ms" not in latency:
            _set_delta(latency, "stt_processing_ms", timestamps, "user.speech.stopped", "transcript.user")
        _set_delta(latency, "speech_to_transcript_ms", timestamps, "user.speech.started", "transcript.user")
        _set_delta(latency, "perceived_latency_ms", timestamps, "transcript.user", "assistant.playback.started")
        _set_delta(latency, "transcript_to_llm_ms", timestamps, "transcript.user", "llm.request.started")
        _set_delta(latency, "transcript_to_tts_audio_ms", timestamps, "transcript.user", "tts.first.audio")

    turn_list = list(turns.values())
    metrics = {
        "perceived_latency_ms": _series(turn_list, "perceived_latency_ms"),
        "provider_ttft_ms": _series(turn_list, "provider_ttft_ms"),
        "stt_processing_ms": _series(turn_list, "stt_processing_ms"),
        "speech_to_transcript_ms": _series(turn_list, "speech_to_transcript_ms"),
        "tts_first_audio_ms": _series(turn_list, "tts_first_audio_ms"),
        "playback_delay_ms": _series(turn_list, "playback_delay_ms"),
        "transcript_to_llm_ms": _series(turn_list, "transcript_to_llm_ms"),
        "transcript_to_tts_audio_ms": _series(turn_list, "transcript_to_tts_audio_ms"),
    }
    client_counts = Counter(
        _canonical_event_name(event.get("event_name"))
        for event in selected
        if _canonical_event_name(event.get("event_name")).startswith(("livekit.client.", "browser.audio.", "hume.client."))
    )
    tool_counts = Counter(
        _canonical_event_name(event.get("event_name"))
        for event in selected
        if _canonical_event_name(event.get("event_name")).startswith("tool.")
    )
    latest_stats = _latest_client_stats(selected)
    return {
        "call_id": call_id,
        "schema": "verbatim.v2.summary",
        "turn_count": len(turn_list),
        "event_count": len(selected),
        "errors": errors,
        "latest_events": selected[-80:],
        "turns": turn_list[-80:],
        "client_event_counts": dict(client_counts),
        "tool_event_counts": dict(tool_counts),
        "tool_call_count": tool_counts.get("tool.call.started", 0) + tool_counts.get("tool.direct.activated", 0),
        "tool_failed_count": tool_counts.get("tool.call.failed", 0),
        "livekit_client_stats": latest_stats,
        **config,
        **{f"avg_{name}": round(mean(values), 1) if values else None for name, values in metrics.items()},
        **{f"p95_{name}": percentile(values, 95) for name, values in metrics.items()},
        **{f"max_{name}": max(values) if values else None for name, values in metrics.items()},
    }


def percentile(values: list[float], pct: int) -> float | None:
    if not values:
        return None
    values = sorted(values)
    index = max(0, min(len(values) - 1, round((pct / 100) * len(values) + 0.499999) - 1))
    return values[index]


def _canonical_event_name(value: Any) -> str:
    return str(value or "").replace("_", ".")


def _series(turns: list[dict[str, Any]], key: str) -> list[float]:
    return [turn["latency"][key] for turn in turns if key in turn.get("latency", {})]


def _set_delta(
    latency: dict[str, float],
    key: str,
    timestamps: dict[str, float | None],
    start_name: str,
    end_name: str,
) -> None:
    start = timestamps.get(start_name)
    end = timestamps.get(end_name)
    if start is None or end is None:
        return
    delta = end - start
    if delta >= 0:
        latency[key] = round(delta, 1)


def _set_metadata_timestamp(timestamps: dict[str, float | None], key: str, value: Any) -> None:
    if value is None:
        return
    try:
        timestamps[key] = float(value)
    except (TypeError, ValueError):
        return


def _set_metadata_latency(latency: dict[str, float], key: str, value: Any) -> None:
    if value is None:
        return
    try:
        latency_ms = float(value)
    except (TypeError, ValueError):
        return
    if latency_ms >= 0:
        latency[key] = round(latency_ms, 1)


def _config_snapshot(events: list[dict[str, Any]]) -> dict[str, Any]:
    configured = next((event for event in events if _canonical_event_name(event.get("event_name")) == "session.configured"), None)
    metadata = configured.get("metadata", {}) if configured else {}
    keys = [
        "transport_provider",
        "room_name",
        "stt_provider",
        "stt_model",
        "llm_provider",
        "llm_model",
        "tts_provider",
        "tts_model",
        "client_id",
        "tools_enabled",
    ]
    return {key: metadata.get(key) for key in keys}


def _latest_client_stats(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(events):
        if _canonical_event_name(event.get("event_name")) == "livekit.client.stats":
            return event.get("metadata") or {}
    return None
