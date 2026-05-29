from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from statistics import mean
from typing import Any, Iterable

from verbatim.analytics.call_notes import generate_call_notes
from verbatim.analytics.latency import summarize_call_events
from verbatim.client_config import client_config_dir
from verbatim.events import safe_metadata


RUBRIC_SCHEMA = "verbatim.v2.evaluation_rubric"
EVALUATION_SCHEMA = "verbatim.v2.evaluation"
CONTEXT_SCHEMA = "verbatim.v2.evaluation_context"
SUMMARY_SCHEMA = "verbatim.v2.evaluation_summary"
RUBRIC_VERSION = 2
DEFAULT_BOT_VERSION = "v0.3.1"


DEFAULT_RUBRIC_FIELDS: tuple[dict[str, Any], ...] = (
    {
        "id": "realism",
        "label": "Realism",
        "description": "Felt like a believable spoken agent with natural timing, tone, and turn-taking.",
    },
    {
        "id": "tool_calling",
        "label": "Tool Calling",
        "description": "Used tools at the right time, checked availability before booking, confirmed writes, and sent SMS only when actually sent.",
    },
    {
        "id": "latency",
        "label": "Latency",
        "description": "Felt responsive with low perceived delay, no awkward silence, and acceptable p95 behavior.",
    },
    {
        "id": "stt",
        "label": "STT",
        "description": "Transcription quality was good enough that errors did not derail the outcome.",
    },
    {
        "id": "intelligence",
        "label": "Intelligence",
        "description": "Understood intent, adapted to context, avoided dumb loops, and answered the actual question.",
    },
    {
        "id": "task_success",
        "label": "Task Success",
        "description": "Advanced toward a useful outcome for the caller and the business.",
    },
    {
        "id": "conversation_flow",
        "label": "Conversation Flow",
        "description": "Avoided form-filling, stale prompt bleed, repetition, and overly pushy follow-up questions.",
    },
    {
        "id": "faithfulness_safety",
        "label": "Faithfulness/Safety",
        "description": "Avoided hallucinated business facts, fake calendar/SMS claims, unsafe writes, and private data leakage.",
    },
)


def evaluation_dir(settings: Any, bot_version: str | None = None) -> Path:
    root = settings.instrumentation.event_log_path.parent / "evaluations"
    if bot_version:
        return root / _safe_bot_version(bot_version)
    return root


def evaluation_runs_dir(settings: Any) -> Path:
    return settings.instrumentation.event_log_path.parent / "evaluation_runs"


def rubric_path() -> Path:
    return client_config_dir() / "evaluation_rubric.json"


def default_rubric() -> dict[str, Any]:
    return {
        "schema": RUBRIC_SCHEMA,
        "version": RUBRIC_VERSION,
        "scale": {"min": 1, "max": 5, "low_needs_attention": 2},
        "benchmark_basis": ["EVA-Bench", "VoiceBench", "SpeechSquad"],
        "focus": "real_estate_demo",
        "fields": deepcopy(list(DEFAULT_RUBRIC_FIELDS)),
    }


def load_rubric() -> dict[str, Any]:
    path = rubric_path()
    fallback = default_rubric()
    if not path.exists():
        _write_json(path, fallback)
        return fallback
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback
    if not isinstance(value, dict) or not isinstance(value.get("fields"), list):
        return fallback
    try:
        loaded_version = int(value.get("version") or 0)
    except (TypeError, ValueError):
        loaded_version = 0
    if loaded_version < RUBRIC_VERSION:
        _write_json(path, fallback)
        return fallback
    return _normalize_rubric(value)


def build_call_evaluation_context(
    settings: Any,
    events: Iterable[dict[str, Any]],
    *,
    call_id: str | None,
    bot_version: str | None = None,
) -> dict[str, Any]:
    selected = [event for event in events if call_id and event.get("call_id") == call_id]
    selected.sort(key=lambda item: item.get("timestamp_monotonic_ms") or 0)
    version = _safe_bot_version(bot_version)
    saved = load_call_evaluation(settings, call_id=call_id, bot_version=bot_version) if call_id else None
    if saved and saved.get("bot_version"):
        version = _safe_bot_version(saved.get("bot_version"))
    return {
        "schema": CONTEXT_SCHEMA,
        "call_id": call_id,
        "bot_version": version,
        "rubric": load_rubric(),
        "auto_metrics": _auto_metrics(summarize_call_events(events, call_id=call_id)),
        "call_notes": generate_call_notes(events, call_id=call_id),
        "transcript": [_transcript_item(event) for event in selected if _transcript_item(event)][-100:],
        "saved_evaluation": saved,
    }


def save_call_evaluation(
    settings: Any,
    events: Iterable[dict[str, Any]],
    *,
    call_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    rubric = load_rubric()
    bot_version = _safe_bot_version(payload.get("bot_version"))
    score_items = _normalize_scores(payload.get("scores") or {}, rubric)
    notes = str(payload.get("reviewer_notes") or "").strip()[:3000]
    report = {
        "schema": EVALUATION_SCHEMA,
        "call_id": call_id,
        "bot_version": bot_version,
        "evaluated_at": datetime.now(UTC).isoformat(),
        "rubric_version": rubric.get("version", RUBRIC_VERSION),
        "rubric_focus": rubric.get("focus", "real_estate_demo"),
        "scores": score_items,
        "score_summary": score_summary(score_items),
        "reviewer_notes": notes,
        "auto_metrics": _auto_metrics(summarize_call_events(events, call_id=call_id)),
    }
    report = safe_metadata(report)
    path = _evaluation_path(settings, call_id, bot_version=bot_version)
    _write_json(path, report)
    return report


def load_call_evaluation(settings: Any, *, call_id: str | None, bot_version: str | None = None) -> dict[str, Any] | None:
    if not call_id:
        return None
    paths = [_evaluation_path(settings, call_id, bot_version=_safe_bot_version(bot_version))] if bot_version else _evaluation_candidate_paths(settings, call_id)
    reports: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            reports.append(value)
    if not reports:
        return None
    reports.sort(key=lambda item: item.get("evaluated_at") or "")
    return reports[-1]


def summarize_evaluations(settings: Any, events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    reports = _load_evaluation_reports(settings)
    reports.sort(key=lambda item: item.get("evaluated_at") or "")
    averages = [float((report.get("score_summary") or {}).get("overall_average")) for report in reports if (report.get("score_summary") or {}).get("overall_average") is not None]
    latest_call_id = None
    for event in reversed(list(events)):
        if event.get("call_id"):
            latest_call_id = str(event["call_id"])
            break
    return {
        "schema": SUMMARY_SCHEMA,
        "evaluation_count": len(reports),
        "latest_call_id": latest_call_id,
        "overall_average": round(mean(averages), 2) if averages else None,
        "needs_attention_count": sum(1 for report in reports if (report.get("score_summary") or {}).get("needs_attention")),
        "versions": _summarize_reports_by_version(reports),
        "reports": reports[-30:],
    }


def score_summary(scores: dict[str, dict[str, Any]]) -> dict[str, Any]:
    values: list[float] = []
    domain_averages: dict[str, float | None] = {}
    needs_attention: list[dict[str, Any]] = []
    for field_id, item in scores.items():
        score = item.get("score")
        domain_averages[field_id] = score
        if score is None:
            continue
        numeric = float(score)
        values.append(numeric)
        if numeric <= 2:
            needs_attention.append({"id": field_id, "label": item.get("label"), "score": score})
    return {
        "overall_average": round(mean(values), 2) if values else None,
        "domain_averages": domain_averages,
        "needs_attention": needs_attention,
    }


def _normalize_rubric(value: dict[str, Any]) -> dict[str, Any]:
    rubric = default_rubric()
    rubric.update({key: value.get(key, rubric[key]) for key in ("schema", "version", "scale", "benchmark_basis", "focus")})
    fields: list[dict[str, Any]] = []
    for raw in value.get("fields") or []:
        if not isinstance(raw, dict):
            continue
        field_id = str(raw.get("id") or "").strip()
        label = str(raw.get("label") or field_id).strip()
        if not field_id or not label:
            continue
        fields.append(
            {
                "id": field_id,
                "label": label,
                "description": str(raw.get("description") or "").strip(),
            }
        )
    rubric["fields"] = fields or deepcopy(list(DEFAULT_RUBRIC_FIELDS))
    return safe_metadata(rubric)


def _normalize_scores(raw_scores: dict[str, Any], rubric: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    fields = rubric.get("fields") or []
    for field in fields:
        field_id = str(field.get("id") or "")
        raw = raw_scores.get(field_id)
        if isinstance(raw, dict):
            raw_score = raw.get("score")
            notes = str(raw.get("notes") or "").strip()[:1000]
        else:
            raw_score = raw
            notes = ""
        score = _coerce_score(raw_score)
        result[field_id] = {
            "label": field.get("label"),
            "score": score,
            "notes": notes,
        }
    return safe_metadata(result)


def _coerce_score(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        score = int(value)
    except (TypeError, ValueError):
        return None
    return max(1, min(5, score))


def _auto_metrics(summary: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "call_id",
        "turn_count",
        "event_count",
        "errors",
        "transport_provider",
        "stt_provider",
        "stt_model",
        "llm_provider",
        "llm_model",
        "tts_provider",
        "tts_model",
        "tools_enabled",
        "tool_call_count",
        "tool_failed_count",
        "tool_turn_count",
        "normal_turn_count",
        "tool_event_counts",
        "avg_perceived_latency_ms",
        "avg_clean_perceived_latency_ms",
        "p95_perceived_latency_ms",
        "max_perceived_latency_ms",
        "latency_peak_threshold_ms",
        "clean_turn_count",
        "peak_turn_count",
        "avg_normal_perceived_latency_ms",
        "avg_clean_normal_perceived_latency_ms",
        "p95_normal_perceived_latency_ms",
        "avg_tool_perceived_latency_ms",
        "avg_clean_tool_perceived_latency_ms",
        "p95_tool_perceived_latency_ms",
        "avg_tool_duration_ms",
        "p95_tool_duration_ms",
        "avg_stt_processing_ms",
        "p95_stt_processing_ms",
        "avg_speech_to_transcript_ms",
        "p95_speech_to_transcript_ms",
        "avg_provider_ttft_ms",
        "p95_provider_ttft_ms",
        "avg_tts_first_audio_ms",
        "p95_tts_first_audio_ms",
        "avg_playback_delay_ms",
        "p95_playback_delay_ms",
        "avg_transcript_to_llm_ms",
        "p95_transcript_to_llm_ms",
        "avg_transcript_to_tts_audio_ms",
        "p95_transcript_to_tts_audio_ms",
        "livekit_client_stats",
    )
    return safe_metadata({key: summary.get(key) for key in keys})


def _transcript_item(event: dict[str, Any]) -> dict[str, Any] | None:
    name = str(event.get("event_name") or "").replace("_", ".")
    if name not in {"transcript.user", "transcript.assistant"}:
        return None
    metadata = event.get("metadata") or {}
    text = str(metadata.get("text") or metadata.get("text_preview") or "").strip()
    if not text:
        return None
    return {
        "role": "user" if name == "transcript.user" else "assistant",
        "text": text[:1000],
        "timestamp": event.get("timestamp_wall_iso"),
    }


def _safe_bot_version(value: Any = None) -> str:
    raw = str(value or DEFAULT_BOT_VERSION).strip().lower()
    raw = re.sub(r"[^a-z0-9._-]+", "-", raw).strip("-._")
    return raw[:40] or DEFAULT_BOT_VERSION


def _evaluation_path(settings: Any, call_id: str, *, bot_version: str | None = None) -> Path:
    safe_call_id = "".join(char for char in str(call_id) if char.isalnum() or char in {"_", "-"}) or "call"
    return evaluation_dir(settings, _safe_bot_version(bot_version)) / f"{safe_call_id}.json"


def _legacy_evaluation_path(settings: Any, call_id: str) -> Path:
    safe_call_id = "".join(char for char in str(call_id) if char.isalnum() or char in {"_", "-"}) or "call"
    return evaluation_dir(settings) / f"{safe_call_id}.json"


def _evaluation_candidate_paths(settings: Any, call_id: str) -> list[Path]:
    root = evaluation_dir(settings)
    candidates = [_legacy_evaluation_path(settings, call_id)]
    if root.exists():
        safe_call_id = "".join(char for char in str(call_id) if char.isalnum() or char in {"_", "-"}) or "call"
        candidates.extend(sorted(path / f"{safe_call_id}.json" for path in root.iterdir() if path.is_dir()))
    return candidates


def _load_evaluation_reports(settings: Any) -> list[dict[str, Any]]:
    root = evaluation_dir(settings)
    if not root.exists():
        return []
    reports: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and value.get("schema") == EVALUATION_SCHEMA:
            value["bot_version"] = _safe_bot_version(value.get("bot_version") or (path.parent.name if path.parent != root else DEFAULT_BOT_VERSION))
            reports.append(value)
    return reports


def _summarize_reports_by_version(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for report in reports:
        grouped.setdefault(_safe_bot_version(report.get("bot_version")), []).append(report)
    summaries: list[dict[str, Any]] = []
    for version, version_reports in sorted(grouped.items()):
        overall_values = [
            float((report.get("score_summary") or {}).get("overall_average"))
            for report in version_reports
            if (report.get("score_summary") or {}).get("overall_average") is not None
        ]
        domain_values: dict[str, list[float]] = {}
        for report in version_reports:
            for field_id, score in ((report.get("score_summary") or {}).get("domain_averages") or {}).items():
                if score is None:
                    continue
                domain_values.setdefault(str(field_id), []).append(float(score))
        summaries.append(
            {
                "bot_version": version,
                "evaluation_count": len(version_reports),
                "overall_average": round(mean(overall_values), 2) if overall_values else None,
                "domain_averages": {
                    field_id: round(mean(values), 2) if values else None
                    for field_id, values in sorted(domain_values.items())
                },
                "needs_attention_count": sum(
                    1 for report in version_reports if (report.get("score_summary") or {}).get("needs_attention")
                ),
                "reports": version_reports[-100:],
            }
        )
    return summaries


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(safe_metadata(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
