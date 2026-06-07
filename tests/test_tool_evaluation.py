from fastapi.testclient import TestClient

from verbatim.analytics.tool_evaluation import (
    FAILURE_SOURCES,
    TOOL_SCENARIOS,
    run_tool_scenarios,
    summarize_tool_evaluation,
)
from verbatim.config import clear_settings_cache
from verbatim.events import append_jsonl
from verbatim.server import create_app


def test_tool_scenario_harness_has_50_cases_and_failure_ranking():
    report = run_tool_scenarios()

    assert len(TOOL_SCENARIOS) == 50
    assert report["scenario_count"] == 50
    assert report["failed_count"] > 0
    assert report["failure_source_ranking"]
    assert report["metrics"]["tool_selection_accuracy_pct"] is not None
    assert report["metrics"]["parameter_accuracy_pct"] is not None
    assert all(item["source"] in FAILURE_SOURCES for item in report["failure_source_ranking"])


def test_tool_evaluation_reconstructs_interaction_and_reality_match():
    events = [
        {
            "call_id": "call_tool",
            "turn_id": "turn_0001",
            "timestamp_monotonic_ms": 1,
            "event_name": "tool.intent.parsed",
            "metadata": {
                "tool_interaction_id": "toolint_1",
                "user_request": "Book Friday at 2 PM.",
                "parsed_intent": "booking",
                "tool_name": "prepare_and_confirm_calendar_booking",
                "tool_arguments": {"start_iso": "2026-06-12T14:00:00+02:00"},
            },
        },
        {
            "call_id": "call_tool",
            "turn_id": "turn_0001",
            "timestamp_monotonic_ms": 2,
            "event_name": "tool.execution.result",
            "metadata": {
                "tool_interaction_id": "toolint_1",
                "tool_name": "prepare_and_confirm_calendar_booking",
                "tool_execution_succeeded": True,
                "ok": True,
                "outcome": "booking_confirmed",
                "booking_booked": True,
            },
        },
        {
            "call_id": "call_tool",
            "turn_id": "turn_0001",
            "timestamp_monotonic_ms": 3,
            "event_name": "tool.assistant.response",
            "metadata": {
                "tool_interaction_id": "toolint_1",
                "assistant_response": "Done, I booked the viewing.",
                "assistant_response_matched_reality": True,
                "assistant_claimed_success": True,
            },
        },
    ]

    summary = summarize_tool_evaluation(events, call_id="call_tool")

    assert summary["interaction_count"] == 1
    assert summary["metrics"]["booking_success_rate_pct"] == 100.0
    assert summary["metrics"]["hallucinated_success_rate_pct"] == 0.0
    assert summary["interactions"][0]["user_request"] == "Book Friday at 2 PM."


def test_tool_evaluation_api_is_browser_safe(monkeypatch, tmp_path):
    event_path = tmp_path / "events.jsonl"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VERBATIM_EVENT_LOG_PATH", str(event_path))
    clear_settings_cache()
    append_jsonl(
        event_path,
        {
            "schema_version": "verbatim.v2",
            "session_id": "sess_tool",
            "call_id": "call_tool",
            "turn_id": "turn_0001",
            "agent_id": "agent",
            "client_id": "client",
            "event_name": "tool.intent.unresolved",
            "timestamp_wall_iso": "2026-06-07T00:00:00+00:00",
            "timestamp_monotonic_ms": 1,
            "provider": "tool",
            "metadata": {
                "tool_interaction_id": "toolint_api",
                "user_request": "Can you book something?",
                "parsed_intent": "unresolved",
                "failure_source": "intent_detection",
            },
        },
    )

    response = TestClient(create_app()).get("/api/analytics/tool-evaluation?call_id=call_tool")

    assert response.status_code == 200
    payload = response.json()
    assert payload["call_id"] == "call_tool"
    assert payload["interaction_count"] == 1
    assert payload["scenario_report"]["scenario_count"] == 50
    assert "api_key" not in str(payload).lower()
