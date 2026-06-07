from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable

from verbatim.integrations.tools import (
    _assistant_response_reality,
    _calendar_action_from_text,
    _calendar_response_text,
    _followup_action_from_text,
    _followup_response_text,
    _parsed_intent_for_action,
)


FAILURE_SOURCES = {
    "A": "Intent detection",
    "B": "Parameter extraction",
    "C": "Tool execution",
    "D": "Tool result handling",
    "E": "Assistant response generation",
}


@dataclass(frozen=True)
class ToolScenario:
    id: str
    category: str
    user_request: str
    recent_text: str = ""
    expected_tool: str | None = None
    expected_intent: str | None = None
    expected_arguments: dict[str, Any] | None = None
    expected_argument_contains: dict[str, str] | None = None
    simulated_result: dict[str, Any] | None = None
    expected_response_contains: str | None = None
    expected_execution_ok: bool | None = None


TOOL_SCENARIOS: list[ToolScenario] = [
    ToolScenario("booking_01", "booking", "Book a viewing tomorrow at 2 PM for this property.", expected_tool="prepare_and_confirm_calendar_booking", expected_intent="booking", expected_argument_contains={"start_iso": "T14:00:00"}),
    ToolScenario("booking_02", "booking", "Schedule it Friday at 7 PM.", recent_text="I want to view this apartment.", expected_tool="prepare_and_confirm_calendar_booking", expected_intent="booking", expected_argument_contains={"start_iso": "T19:00:00"}),
    ToolScenario("booking_03", "booking", "Can you put it in the calendar for May 23rd at 7 PM?", recent_text="This property works.", expected_tool="prepare_and_confirm_calendar_booking", expected_intent="booking", expected_argument_contains={"start_iso": "T19:00:00"}),
    ToolScenario("booking_04", "booking", "Let's do it at 10 AM tomorrow.", recent_text="Can I book a viewing for this property?", expected_tool="prepare_and_confirm_calendar_booking", expected_intent="booking", expected_argument_contains={"start_iso": "T10:00:00"}),
    ToolScenario("booking_05", "booking", "Add a property viewing on June 20th at 4 PM.", expected_tool="prepare_and_confirm_calendar_booking", expected_intent="booking", expected_argument_contains={"start_iso": "T16:00:00"}),
    ToolScenario("booking_06", "booking", "Please create an appointment for Wednesday at 11 AM.", recent_text="I want to see that listing.", expected_tool="prepare_and_confirm_calendar_booking", expected_intent="booking", expected_argument_contains={"start_iso": "T11:00:00"}),
    ToolScenario("booking_07", "booking", "Book that one for next Monday at 9 AM.", recent_text="The property in Marina looks good.", expected_tool="prepare_and_confirm_calendar_booking", expected_intent="booking", expected_argument_contains={"start_iso": "T09:00:00"}),
    ToolScenario("booking_08", "booking", "Set up the viewing at 3 PM on June 15th.", recent_text="The villa called Palm View.", expected_tool="prepare_and_confirm_calendar_booking", expected_intent="booking", expected_argument_contains={"start_iso": "T15:00:00"}),
    ToolScenario("reschedule_01", "rescheduling", "Reschedule the viewing to Friday at 3 PM.", expected_tool="prepare_and_confirm_calendar_booking", expected_intent="booking", expected_argument_contains={"start_iso": "T15:00:00"}),
    ToolScenario("reschedule_02", "rescheduling", "Move my appointment to tomorrow at noon.", expected_tool="prepare_and_confirm_calendar_booking", expected_intent="booking", expected_argument_contains={"start_iso": "T12:00:00"}),
    ToolScenario("reschedule_03", "rescheduling", "Actually make it next week Tuesday at 5 PM instead.", recent_text="I booked a viewing.", expected_tool="prepare_and_confirm_calendar_booking", expected_intent="booking", expected_argument_contains={"start_iso": "T17:00:00"}),
    ToolScenario("reschedule_04", "rescheduling", "Can we change the booking to 6 PM?", recent_text="The viewing is on Friday.", expected_tool="prepare_and_confirm_calendar_booking", expected_intent="booking", expected_argument_contains={"start_iso": "T18:00:00"}),
    ToolScenario("cancellation_01", "cancellation", "Cancel the booking.", expected_tool="cancel_calendar_booking", expected_intent="cancellation"),
    ToolScenario("cancellation_02", "cancellation", "Please remove the viewing from the calendar.", expected_tool="cancel_calendar_booking", expected_intent="cancellation"),
    ToolScenario("cancellation_03", "cancellation", "Take it off my calendar.", expected_tool="cancel_calendar_booking", expected_intent="cancellation"),
    ToolScenario("cancellation_04", "cancellation", "Delete that appointment.", expected_tool="cancel_calendar_booking", expected_intent="cancellation"),
    ToolScenario("availability_01", "availability", "Are you free Friday at 2 PM?", expected_tool="check_calendar_conflict", expected_intent="availability_lookup", expected_argument_contains={"start_iso": "T14:00:00"}),
    ToolScenario("availability_02", "availability", "Can I come by tomorrow at 11 AM?", expected_tool="check_calendar_conflict", expected_intent="availability_lookup", expected_argument_contains={"start_iso": "T11:00:00"}),
    ToolScenario("availability_03", "availability", "Do you have any slots next week?", recent_text="I want to view the property.", expected_tool="check_calendar_availability", expected_intent="availability_lookup"),
    ToolScenario("availability_04", "availability", "What availability do you have on June 25th?", expected_tool="check_calendar_availability", expected_intent="availability_lookup", expected_arguments={"date_iso": True}),
    ToolScenario("availability_05", "availability", "Is 4 PM open?", recent_text="Can we do a viewing on Friday?", expected_tool="check_calendar_conflict", expected_intent="availability_lookup", expected_argument_contains={"start_iso": "T16:00:00"}),
    ToolScenario("availability_06", "availability", "Can we do that time?", recent_text="Friday at 3 PM for the viewing.", expected_tool="check_calendar_conflict", expected_intent="availability_lookup", expected_argument_contains={"start_iso": "T15:00:00"}),
    ToolScenario("ambiguous_01", "ambiguous_dates", "Can we do next week?", recent_text="I want to visit the property.", expected_tool="check_calendar_availability", expected_intent="availability_lookup"),
    ToolScenario("ambiguous_02", "ambiguous_dates", "Maybe Friday.", recent_text="I want to book a viewing.", expected_tool="prepare_and_confirm_calendar_booking", expected_intent="missing_information", expected_arguments={"missing_time": True}),
    ToolScenario("ambiguous_03", "ambiguous_dates", "At 7 PM.", recent_text="Book a viewing next Friday for this property.", expected_tool="prepare_and_confirm_calendar_booking", expected_intent="booking", expected_argument_contains={"start_iso": "T19:00:00"}),
    ToolScenario("ambiguous_04", "ambiguous_dates", "Sometime tomorrow.", recent_text="Can I book a viewing for this property?", expected_tool="prepare_and_confirm_calendar_booking", expected_intent="missing_information", expected_arguments={"missing_time": True}),
    ToolScenario("ambiguous_05", "ambiguous_dates", "Book it later.", recent_text="This property is good.", expected_tool="prepare_and_confirm_calendar_booking", expected_intent="missing_information", expected_arguments={"missing_details": True}),
    ToolScenario("missing_01", "missing_information", "Book a viewing.", expected_tool="prepare_and_confirm_calendar_booking", expected_intent="missing_information", expected_arguments={"missing_details": True}),
    ToolScenario("missing_02", "missing_information", "Schedule it tomorrow.", recent_text="This property works.", expected_tool="prepare_and_confirm_calendar_booking", expected_intent="missing_information", expected_arguments={"missing_time": True}),
    ToolScenario("missing_03", "missing_information", "Book it at 2 PM.", recent_text="This property works.", expected_tool="prepare_and_confirm_calendar_booking", expected_intent="missing_information", expected_arguments={"missing_day": True}),
    ToolScenario("missing_04", "missing_information", "Can I view this property?", expected_tool="check_calendar_availability", expected_intent="availability_lookup", expected_arguments={"requires_property_context": True}),
    ToolScenario("missing_05", "missing_information", "Send me details.", expected_tool="send_sms_followup", expected_intent="sms_followup"),
    ToolScenario("invalid_01", "invalid_requests", "Book it for February 31st at 2 PM.", recent_text="This property works.", expected_tool="prepare_and_confirm_calendar_booking", expected_intent="missing_information", expected_arguments={"missing_day": True}),
    ToolScenario("invalid_02", "invalid_requests", "Book it at 25 PM tomorrow.", recent_text="This property works.", expected_tool="prepare_and_confirm_calendar_booking", expected_intent="missing_information", expected_arguments={"missing_time": True}),
    ToolScenario("invalid_03", "invalid_requests", "Cancel every appointment on the calendar.", expected_tool="cancel_calendar_booking", expected_intent="cancellation"),
    ToolScenario("invalid_04", "invalid_requests", "Read me everything on your calendar.", expected_tool="unsupported_calendar_read", expected_intent="unsupported_calendar_read"),
    ToolScenario("invalid_05", "invalid_requests", "Book a viewing before I know the price.", expected_tool=None),
    ToolScenario("double_01", "double_bookings", "Is it already booked?", recent_text="I booked a viewing for Friday at 2 PM.", expected_tool=None),
    ToolScenario("double_02", "double_bookings", "What about the booking? It does not seem booked.", recent_text="Friday at 2 PM.", expected_tool=None),
    ToolScenario("double_03", "double_bookings", "Book it again for Friday at 2 PM.", recent_text="The viewing is already booked.", expected_tool="prepare_and_confirm_calendar_booking", expected_intent="booking", expected_argument_contains={"start_iso": "T14:00:00"}),
    ToolScenario("double_04", "double_bookings", "Are you already busy Friday at 2 PM?", expected_tool="check_calendar_conflict", expected_intent="availability_lookup", expected_argument_contains={"start_iso": "T14:00:00"}),
    ToolScenario("double_05", "double_bookings", "Can you check if there is a conflict at 10 AM tomorrow?", expected_tool="check_calendar_conflict", expected_intent="conflict_check", expected_argument_contains={"start_iso": "T10:00:00"}),
    ToolScenario("sms_01", "sms_followup", "Send me the viewing confirmation.", expected_tool="send_sms_followup", expected_intent="sms_followup"),
    ToolScenario("sms_02", "sms_followup", "Text me the address.", recent_text="The property is Palm View.", expected_tool="send_sms_followup", expected_intent="sms_followup"),
    ToolScenario("sms_03", "sms_followup", "Can you send property details?", recent_text="The apartment is Marina Gate.", expected_tool="send_sms_followup", expected_intent="sms_followup"),
    ToolScenario("sms_04", "sms_followup", "Did you send the confirmation?", expected_tool="send_sms_followup", expected_intent="sms_followup"),
    ToolScenario("sms_05", "sms_followup", "Send that to me by WhatsApp.", expected_tool="send_sms_followup", expected_intent="sms_followup"),
    ToolScenario("correction_01", "user_correction", "Actually no, not Friday.", recent_text="I can do Friday at 2 PM.", expected_tool=None),
    ToolScenario("correction_02", "user_correction", "Wait, make it Saturday at 1 PM.", recent_text="Book a viewing Friday at 2 PM.", expected_tool="prepare_and_confirm_calendar_booking", expected_intent="booking", expected_argument_contains={"start_iso": "T13:00:00"}),
    ToolScenario("correction_03", "user_correction", "No, do not book it yet.", recent_text="Book it tomorrow at 2 PM.", expected_tool=None),
]


def summarize_tool_evaluation(events: Iterable[dict[str, Any]], *, call_id: str | None = None) -> dict[str, Any]:
    selected = [event for event in events if not call_id or event.get("call_id") == call_id]
    selected.sort(key=lambda item: item.get("timestamp_monotonic_ms") or 0)
    interactions = _tool_interactions_from_events(selected)
    scenario_report = run_tool_scenarios()
    return {
        "schema": "verbatim.v2.tool_evaluation",
        "call_id": call_id,
        "interaction_count": len(interactions),
        "interactions": interactions[-80:],
        "metrics": _tool_metrics(interactions),
        "scenario_report": scenario_report,
    }


def run_tool_scenarios() -> dict[str, Any]:
    results = [evaluate_tool_scenario(scenario) for scenario in TOOL_SCENARIOS]
    failures = [result for result in results if not result["passed"]]
    counts = Counter(result["failure_source"] for result in failures if result.get("failure_source"))
    parameter_candidates = [
        result
        for result in results
        if result.get("expected_tool") and result.get("failure_source") != "A"
    ]
    booking_candidates = [
        result
        for result in results
        if result.get("expected_tool") == "prepare_and_confirm_calendar_booking"
    ]
    sms_candidates = [result for result in results if result.get("expected_tool") == "send_sms_followup"]
    return {
        "schema": "verbatim.v2.tool_scenario_report",
        "scenario_count": len(results),
        "passed_count": len(results) - len(failures),
        "failed_count": len(failures),
        "pass_rate_pct": _pct(len(results) - len(failures), len(results)),
        "metrics": {
            "tool_selection_accuracy_pct": _pct(sum(1 for result in results if result.get("failure_source") != "A"), len(results)),
            "parameter_accuracy_pct": _pct(
                sum(1 for result in parameter_candidates if result.get("failure_source") != "B"),
                len(parameter_candidates),
            ),
            "hallucinated_success_rate_pct": _pct(counts.get("E", 0), len(results)),
            "tool_execution_failure_rate_pct": _pct(counts.get("C", 0), len(results)),
            "booking_success_rate_pct": _pct(sum(1 for result in booking_candidates if result["passed"]), len(booking_candidates)),
            "sms_success_rate_pct": _pct(sum(1 for result in sms_candidates if result["passed"]), len(sms_candidates)),
        },
        "failure_source_counts": dict(counts),
        "failure_source_ranking": [
            {"source": source, "label": FAILURE_SOURCES.get(source, source), "count": count}
            for source, count in counts.most_common()
        ],
        "category_counts": dict(Counter(result["category"] for result in results)),
        "results": results,
    }


def evaluate_tool_scenario(scenario: ToolScenario) -> dict[str, Any]:
    action = _scenario_action(scenario)
    actual_tool = action.get("tool_name") if action else None
    actual_intent = _parsed_intent_for_action(action, latest_text=scenario.user_request) if action else None
    failure_source = None
    failure_reason = None

    if actual_tool != scenario.expected_tool:
        failure_source = "A"
        failure_reason = f"expected tool {scenario.expected_tool or 'none'}, got {actual_tool or 'none'}"
    elif scenario.expected_intent and actual_intent != scenario.expected_intent:
        failure_source = "A"
        failure_reason = f"expected intent {scenario.expected_intent}, got {actual_intent or 'none'}"
    elif action and not _arguments_match(action.get("arguments") or {}, scenario):
        failure_source = "B"
        failure_reason = "tool arguments did not match expected constraints"

    response = None
    result = scenario.simulated_result
    if action and not failure_source:
        result = result or _default_result_for_action(action)
        if scenario.expected_execution_ok is True and not result.get("ok"):
            failure_source = "C"
            failure_reason = f"tool execution outcome was {result.get('outcome') or 'unknown'}"
        elif scenario.expected_execution_ok is False and result.get("ok"):
            failure_source = "C"
            failure_reason = "tool execution succeeded when scenario expected failure"
        response = _response_for_action(action, result)
        if scenario.expected_response_contains and scenario.expected_response_contains.lower() not in response.lower():
            failure_source = failure_source or "D"
            failure_reason = failure_reason or "assistant response did not reflect expected tool result"
        reality = _assistant_response_reality(response, result)
        if not reality.get("assistant_response_matched_reality"):
            failure_source = failure_source or "E"
            failure_reason = failure_reason or str(reality.get("assistant_mismatch_reason") or "assistant response did not match reality")

    return {
        "id": scenario.id,
        "category": scenario.category,
        "user_request": scenario.user_request,
        "expected_tool": scenario.expected_tool,
        "actual_tool": actual_tool,
        "expected_intent": scenario.expected_intent,
        "actual_intent": actual_intent,
        "actual_arguments": action.get("arguments") if action else None,
        "tool_execution_result": result,
        "assistant_response": response,
        "passed": failure_source is None,
        "failure_source": failure_source,
        "failure_source_label": FAILURE_SOURCES.get(failure_source or "", None),
        "failure_reason": failure_reason,
    }


def _scenario_action(scenario: ToolScenario) -> dict[str, Any] | None:
    followup = _followup_action_from_text(
        latest_text=scenario.user_request,
        recent_text=scenario.recent_text,
        default_phone="+33600000000",
        default_email=None,
        sms_body="Test follow-up.",
        email_subject="Test",
        email_body="Test",
    )
    if followup:
        return followup
    return _calendar_action_from_text(latest_text=scenario.user_request, recent_text=f"{scenario.recent_text} {scenario.user_request}".strip())


def _arguments_match(arguments: dict[str, Any], scenario: ToolScenario) -> bool:
    for key, expected in (scenario.expected_arguments or {}).items():
        value = arguments.get(key)
        if expected is True and not value:
            return False
        if expected is False and value:
            return False
        if expected not in {True, False} and value != expected:
            return False
    for key, expected in (scenario.expected_argument_contains or {}).items():
        if expected not in str(arguments.get(key) or ""):
            return False
    return True


def _default_result_for_action(action: dict[str, Any]) -> dict[str, Any]:
    tool = action.get("tool_name")
    arguments = action.get("arguments") or {}
    if arguments.get("missing_details"):
        return {"ok": False, "outcome": "missing_booking_details"}
    if tool == "check_calendar_availability":
        return {
            "ok": True,
            "outcome": "available_slots",
            "slots": [{"start_iso": "2026-06-15T10:00:00+02:00", "end_iso": "2026-06-15T10:30:00+02:00"}],
        }
    if tool == "check_calendar_conflict":
        return {
            "ok": True,
            "outcome": "calendar_conflict_checked",
            "has_conflict": False,
            "checked_slot": {
                "start_iso": arguments.get("start_iso") or "2026-06-15T10:00:00+02:00",
                "end_iso": arguments.get("end_iso") or "2026-06-15T10:30:00+02:00",
            },
        }
    if tool == "prepare_and_confirm_calendar_booking":
        return {
            "ok": True,
            "outcome": "booking_confirmed",
            "booking": {
                "id": "booking_test",
                "external_event_id": "event_test",
                "start_iso": arguments.get("start_iso"),
                "end_iso": arguments.get("end_iso"),
            },
        }
    if tool == "cancel_calendar_booking":
        return {"ok": True, "outcome": "booking_cancelled"}
    if tool == "send_sms_followup":
        return {"ok": True, "outcome": "sms_sent", "destination_preview": "***0000", "message_id": "SM_test"}
    if tool == "unsupported_calendar_read":
        return {"ok": False, "outcome": "unsupported_calendar_read"}
    return {"ok": False, "outcome": "unknown_tool"}


def _response_for_action(action: dict[str, Any], result: dict[str, Any]) -> str:
    if action.get("tool_name") == "send_sms_followup":
        return _followup_response_text(action, result)
    return _calendar_response_text(action, result)


def _tool_interactions_from_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    ordered_ids: list[str] = []
    for event in events:
        name = str(event.get("event_name") or "").replace("_", ".")
        metadata = event.get("metadata") or {}
        interaction_id = str(metadata.get("tool_interaction_id") or "").strip()
        if not interaction_id:
            continue
        if interaction_id not in by_id:
            by_id[interaction_id] = {
                "tool_interaction_id": interaction_id,
                "call_id": event.get("call_id"),
                "turn_id": event.get("turn_id"),
                "events": [],
            }
            ordered_ids.append(interaction_id)
        item = by_id[interaction_id]
        item["events"].append(name)
        if name in {"tool.intent.parsed", "tool.intent.unresolved", "tool.direct.activated", "tool.direct.skipped"}:
            item["user_request"] = metadata.get("user_request") or metadata.get("text_preview") or item.get("user_request")
            item["parsed_intent"] = metadata.get("parsed_intent") or item.get("parsed_intent")
            item["tool_selected"] = metadata.get("tool_name") or item.get("tool_selected")
            item["tool_arguments"] = metadata.get("tool_arguments") or item.get("tool_arguments")
        if name in {"tool.execution.result", "tool.call.completed", "tool.call.failed"}:
            item["execution_result"] = {
                "ok": metadata.get("ok"),
                "outcome": metadata.get("outcome") or metadata.get("tool_result_outcome"),
                "booking_booked": metadata.get("booking_booked"),
                "booking_cancelled": metadata.get("booking_cancelled"),
                "sms_sent": metadata.get("sms_sent"),
                "calendar_checked": metadata.get("calendar_checked"),
                "duration_ms": metadata.get("duration_ms"),
            }
            item["execution_succeeded"] = bool(metadata.get("ok"))
        if name == "tool.assistant.response":
            item["assistant_response"] = metadata.get("assistant_response") or metadata.get("text_preview")
            item["assistant_response_matched_reality"] = metadata.get("assistant_response_matched_reality")
            item["assistant_mismatch_reason"] = metadata.get("assistant_mismatch_reason")
            item["assistant_claimed_success"] = metadata.get("assistant_claimed_success")
        if metadata.get("failure_source"):
            item["failure_source"] = metadata.get("failure_source")
    return [by_id[key] for key in ordered_ids]


def _tool_metrics(interactions: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(interactions)
    executed = [item for item in interactions if item.get("execution_result")]
    execution_failed = [item for item in executed if not item.get("execution_succeeded")]
    hallucinated = [item for item in interactions if item.get("assistant_response_matched_reality") is False]
    booking_attempts = [item for item in interactions if item.get("tool_selected") in {"prepare_and_confirm_calendar_booking", "confirm_calendar_booking", "prepare_calendar_booking"}]
    booking_success = [item for item in booking_attempts if (item.get("execution_result") or {}).get("booking_booked")]
    sms_attempts = [item for item in interactions if item.get("tool_selected") == "send_sms_followup"]
    sms_success = [item for item in sms_attempts if (item.get("execution_result") or {}).get("sms_sent")]
    known_selection = [item for item in interactions if "tool_selection_correct" in item]
    known_params = [item for item in interactions if "parameter_correct" in item]
    return {
        "tool_selection_accuracy_pct": _known_pct(known_selection, "tool_selection_correct"),
        "parameter_accuracy_pct": _known_pct(known_params, "parameter_correct"),
        "hallucinated_success_rate_pct": _pct(len(hallucinated), total),
        "tool_execution_failure_rate_pct": _pct(len(execution_failed), len(executed)),
        "booking_success_rate_pct": _pct(len(booking_success), len(booking_attempts)),
        "sms_success_rate_pct": _pct(len(sms_success), len(sms_attempts)),
        "interaction_count": total,
        "executed_count": len(executed),
        "execution_failed_count": len(execution_failed),
        "hallucinated_success_count": len(hallucinated),
        "booking_attempt_count": len(booking_attempts),
        "booking_success_count": len(booking_success),
        "sms_attempt_count": len(sms_attempts),
        "sms_success_count": len(sms_success),
    }


def _known_pct(items: list[dict[str, Any]], key: str) -> float | None:
    if not items:
        return None
    return _pct(sum(1 for item in items if item.get(key)), len(items))


def _pct(part: int, total: int) -> float | None:
    if not total:
        return None
    return round((part / total) * 100, 1)
