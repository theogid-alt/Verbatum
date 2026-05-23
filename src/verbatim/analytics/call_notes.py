from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any, Iterable


def generate_call_notes(events: Iterable[dict[str, Any]], *, call_id: str | None = None) -> dict[str, Any]:
    selected = [event for event in events if not call_id or event.get("call_id") == call_id]
    selected.sort(key=lambda item: item.get("timestamp_monotonic_ms") or 0)
    transcript = [_transcript_item(event) for event in selected]
    transcript = [item for item in transcript if item]
    tool_events = [_tool_item(event) for event in selected if _event_name(event).startswith("tool.")]
    tool_events = [item for item in tool_events if item]
    errors = [_error_item(event) for event in selected if _event_name(event) == "error"]
    errors = [item for item in errors if item]
    outcome = _call_outcome(selected)
    role_counts = Counter(item["role"] for item in transcript)
    notes_text = _notes_text(
        outcome=outcome,
        transcript=transcript,
        tool_events=tool_events,
        errors=errors,
        user_turns=role_counts.get("user", 0),
        assistant_turns=role_counts.get("assistant", 0),
    )
    return {
        "schema": "verbatim.v2.call_notes",
        "call_id": call_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "ready" if transcript or tool_events or errors else "waiting",
        "outcome": outcome,
        "user_turns": role_counts.get("user", 0),
        "assistant_turns": role_counts.get("assistant", 0),
        "tool_event_count": len(tool_events),
        "error_count": len(errors),
        "notes_text": notes_text,
        "highlights": _highlights(transcript),
        "next_steps": _next_steps(transcript, tool_events),
        "tools": tool_events[-12:],
        "errors": errors[-6:],
        "transcript_excerpt": transcript[-12:],
    }


def _notes_text(
    *,
    outcome: str,
    transcript: list[dict[str, str]],
    tool_events: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    user_turns: int,
    assistant_turns: int,
) -> str:
    if not transcript and not tool_events and not errors:
        return "Summary will appear after the call has transcript or tool activity."
    lines: list[str] = []
    user_focus = _user_focus(transcript)
    assistant_close = _last_text(transcript, role="assistant")
    tool_summary = _brief_tool_summary(tool_events)
    if user_focus:
        lines.append(f"Caller: {_clip(user_focus, 150)}")
    if tool_summary:
        lines.append(tool_summary)
    elif assistant_close:
        lines.append(f"Agent: {_clip(assistant_close, 150)}")
    if errors:
        lines.append(f"{len(errors)} error{'s' if len(errors) != 1 else ''} recorded.")
    if outcome not in {"unknown", "active"}:
        lines.append(f"Call ended: {outcome}.")
    if not lines:
        lines.append(f"Conversation had {user_turns} user turn{'s' if user_turns != 1 else ''}.")
    return " ".join(lines)


def _last_text(transcript: list[dict[str, str]], *, role: str) -> str | None:
    for item in reversed(transcript):
        if item["role"] == role and item["text"]:
            return item["text"]
    return None


def _user_focus(transcript: list[dict[str, str]]) -> str | None:
    action_words = (
        "book",
        "appointment",
        "viewing",
        "price",
        "available",
        "availability",
        "calendar",
        "sms",
        "text",
        "confirmation",
        "send",
    )
    filler = {"okay", "wonderful", "amazing", "great", "thanks", "thank you", "yes", "no"}
    user_texts = [item["text"] for item in transcript if item["role"] == "user" and item["text"]]
    for text in reversed(user_texts):
        lowered = text.lower().strip(" .!?")
        if lowered in filler:
            continue
        if any(word in lowered for word in action_words):
            return text
    for text in reversed(user_texts):
        lowered = text.lower().strip(" .!?")
        if lowered not in filler:
            return text
    return None


def _brief_tool_summary(tool_events: list[dict[str, Any]]) -> str | None:
    terminal = [item for item in tool_events if item["event"] in {"tool.call.completed", "tool.call.failed"}]
    if terminal:
        latest = terminal[-1]
        tool_name = str(latest.get("tool_name") or "tool")
        raw_outcome = str(latest.get("outcome") or "completed")
        outcome = raw_outcome.replace("_", " ")
        if latest["event"] == "tool.call.failed":
            if tool_name == "confirm_calendar_booking":
                return f"Booking was not completed: {outcome}."
            return f"{tool_name} failed: {outcome}."
        if "confirmation_required" in raw_outcome:
            return "Booking still needs confirmation."
        if tool_name == "confirm_calendar_booking" and "booking" in outcome:
            return "Calendar booking succeeded."
        if tool_name == "send_sms_followup" and "sms" in outcome:
            return "SMS confirmation was sent."
        return f"{tool_name} succeeded: {outcome}."
    return None


def _highlights(transcript: list[dict[str, str]]) -> list[str]:
    highlights: list[str] = []
    for item in transcript[-10:]:
        text = item["text"]
        if not text:
            continue
        highlights.append(f"{item['role'].title()}: {_clip(text, 180)}")
    return highlights[-8:]


def _next_steps(transcript: list[dict[str, str]], tool_events: list[dict[str, Any]]) -> list[str]:
    steps: list[str] = []
    for item in tool_events:
        outcome = str(item.get("outcome") or "").replace("_", " ")
        tool_name = str(item.get("tool_name") or "tool")
        if outcome:
            steps.append(f"{tool_name}: {outcome}.")
    follow_up_words = ("sms", "text", "whatsapp", "send", "confirmation", "viewing", "book", "calendar", "follow")
    for item in transcript:
        if item["role"] != "assistant":
            continue
        text = item["text"]
        if any(word in text.lower() for word in follow_up_words):
            steps.append(_clip(text, 160))
    deduped: list[str] = []
    seen: set[str] = set()
    for step in steps:
        normalized = step.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(step)
    return deduped[-5:]


def _transcript_item(event: dict[str, Any]) -> dict[str, str] | None:
    name = _event_name(event)
    if name not in {"transcript.user", "transcript.assistant"}:
        return None
    metadata = event.get("metadata") or {}
    text = str(metadata.get("text") or metadata.get("text_preview") or "").strip()
    if not text:
        return None
    return {
        "role": "user" if name == "transcript.user" else "assistant",
        "text": _clip(text, 500),
        "timestamp": str(event.get("timestamp_wall_iso") or ""),
    }


def _tool_item(event: dict[str, Any]) -> dict[str, Any] | None:
    metadata = event.get("metadata") or {}
    return {
        "event": _event_name(event),
        "tool_name": metadata.get("tool_name"),
        "outcome": metadata.get("outcome"),
        "duration_ms": metadata.get("duration_ms"),
        "timestamp": event.get("timestamp_wall_iso"),
    }


def _error_item(event: dict[str, Any]) -> dict[str, Any] | None:
    metadata = event.get("metadata") or {}
    return {
        "error_type": metadata.get("error_type"),
        "error_message": _clip(str(metadata.get("error_message") or ""), 220),
        "timestamp": event.get("timestamp_wall_iso"),
    }


def _call_outcome(events: list[dict[str, Any]]) -> str:
    for event in reversed(events):
        if _event_name(event) == "session.ended":
            return str((event.get("metadata") or {}).get("outcome") or "ended")
    return "active" if events else "unknown"


def _event_name(event: dict[str, Any]) -> str:
    return str(event.get("event_name") or "").replace("_", ".")


def _clip(value: str, limit: int) -> str:
    value = " ".join(value.split())
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."
