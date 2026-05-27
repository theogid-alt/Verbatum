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
        if name.startswith("tool."):
            turn["metadata"]["has_tool_turn"] = True
            if name == "tool.call.failed":
                turn["metadata"]["has_tool_failure"] = True
            if metadata.get("duration_ms") is not None:
                _set_metadata_latency(turn["latency"], "tool_duration_ms", metadata.get("duration_ms"))
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
        "tool_duration_ms": _series(turn_list, "tool_duration_ms"),
    }
    tool_turns = [turn for turn in turn_list if turn.get("metadata", {}).get("has_tool_turn")]
    normal_turns = [turn for turn in turn_list if not turn.get("metadata", {}).get("has_tool_turn")]
    tool_perceived = _series(tool_turns, "perceived_latency_ms")
    normal_perceived = _series(normal_turns, "perceived_latency_ms")
    clean_perceived = _without_peaks(metrics["perceived_latency_ms"])
    clean_normal_perceived = _without_peaks(normal_perceived)
    clean_tool_perceived = _without_peaks(tool_perceived)
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
        "tool_turn_count": len(tool_turns),
        "normal_turn_count": len(normal_turns),
        "latency_peak_threshold_ms": 2000,
        "clean_turn_count": len(clean_perceived),
        "peak_turn_count": len(metrics["perceived_latency_ms"]) - len(clean_perceived),
        "avg_clean_perceived_latency_ms": round(mean(clean_perceived), 1) if clean_perceived else None,
        "avg_tool_perceived_latency_ms": round(mean(tool_perceived), 1) if tool_perceived else None,
        "avg_clean_tool_perceived_latency_ms": round(mean(clean_tool_perceived), 1) if clean_tool_perceived else None,
        "p95_tool_perceived_latency_ms": percentile(tool_perceived, 95),
        "max_tool_perceived_latency_ms": max(tool_perceived) if tool_perceived else None,
        "avg_normal_perceived_latency_ms": round(mean(normal_perceived), 1) if normal_perceived else None,
        "avg_clean_normal_perceived_latency_ms": round(mean(clean_normal_perceived), 1) if clean_normal_perceived else None,
        "p95_normal_perceived_latency_ms": percentile(normal_perceived, 95),
        "max_normal_perceived_latency_ms": max(normal_perceived) if normal_perceived else None,
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


def _without_peaks(values: list[float], *, threshold_ms: float = 2000) -> list[float]:
    return [value for value in values if value <= threshold_ms]


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
