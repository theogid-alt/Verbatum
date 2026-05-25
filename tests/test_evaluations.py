from fastapi.testclient import TestClient

from verbatim.analytics.evaluation import load_rubric, save_call_evaluation, score_summary, summarize_evaluations
from verbatim.config import Settings, clear_settings_cache, get_settings
from verbatim.events import load_events
import verbatim.server as server
from verbatim.server import create_app


def test_default_rubric_file_is_created(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    rubric = load_rubric()

    assert rubric["schema"] == "verbatim.v2.evaluation_rubric"
    assert len(rubric["fields"]) == 8
    assert {field["id"] for field in rubric["fields"]} >= {"realism", "tool_calling", "latency", "stt", "intelligence"}
    assert (tmp_path / "client" / "evaluation_rubric.json").exists()


def test_score_summary_calculates_average_and_attention_flags():
    summary = score_summary(
        {
            "realism": {"label": "Realism", "score": 5},
            "tool_calling": {"label": "Tool Calling", "score": 2},
            "conversation_flow": {"label": "Conversation Flow", "score": None},
        }
    )

    assert summary["overall_average"] == 3.5
    assert summary["domain_averages"]["conversation_flow"] is None
    assert summary["needs_attention"] == [{"id": "tool_calling", "label": "Tool Calling", "score": 2}]


def test_evaluation_report_serializes_scores_metrics_and_redacts(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    settings = Settings.from_env(
        {
            "VERBATIM_EVENT_LOG_PATH": str(tmp_path / "data" / "events.jsonl"),
        }
    )
    events = [
        event("call_a", "turn_0001", "transcript.user", 1000),
        event("call_a", "turn_0001", "assistant.playback.started", 1400),
    ]

    report = save_call_evaluation(
        settings,
        events,
        call_id="call_a",
        payload={
            "scores": {
                "realism": {"score": 5, "notes": "Good"},
                "tool_calling": {"score": 2, "api_key": "secret"},
            },
            "bot_version": "v02",
            "reviewer_notes": "Useful call.",
            "api_key": "secret",
        },
    )

    assert report["schema"] == "verbatim.v2.evaluation"
    assert report["bot_version"] == "v02"
    assert report["score_summary"]["overall_average"] == 3.5
    assert report["score_summary"]["needs_attention"][0]["id"] == "tool_calling"
    assert report["auto_metrics"]["avg_perceived_latency_ms"] == 400
    assert "secret" not in str(report)
    saved = load_events(tmp_path / "data" / "evaluations" / "v02" / "call_a.json")
    assert saved == []
    assert (tmp_path / "data" / "evaluations" / "v02" / "call_a.json").exists()


def test_evaluation_api_returns_empty_draft_for_missing_call(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VERBATIM_EVENT_LOG_PATH", str(tmp_path / "events.jsonl"))
    clear_settings_cache()

    response = TestClient(create_app()).get("/api/evaluations/call?call_id=missing")

    assert response.status_code == 200
    payload = response.json()
    assert payload["call_id"] == "missing"
    assert payload["transcript"] == []
    assert payload["call_notes"]["status"] == "waiting"
    assert payload["saved_evaluation"] is None


def test_evaluation_api_saves_and_reloads_without_touching_agent(monkeypatch, tmp_path):
    class FakeProcess:
        pid = 1234
        returncode = None

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VERBATIM_EVENT_LOG_PATH", str(tmp_path / "events.jsonl"))
    clear_settings_cache()
    settings = get_settings()
    sink = server._sink(settings, "call_eval", "sess_eval")
    sink.emit("transcript.user", turn_id="turn_0001", metadata={"text": "Can you book a viewing?"})
    sink.emit("assistant.playback.started", turn_id="turn_0001")
    server.ACTIVE_AGENT.clear()
    server.ACTIVE_AGENT["live_call"] = server.ActiveAgent(process=FakeProcess())
    client = TestClient(create_app())

    save_response = client.put(
        "/api/evaluations/call/call_eval",
        json={"bot_version": "v01", "scores": {"realism": 4, "conversation_flow": {"score": 2, "notes": "Repetitive"}}},
    )
    reload_response = client.get("/api/evaluations/call?call_id=call_eval")

    assert save_response.status_code == 200
    assert reload_response.status_code == 200
    assert server.ACTIVE_AGENT["live_call"].process.pid == 1234
    saved = reload_response.json()["saved_evaluation"]
    assert saved["bot_version"] == "v01"
    assert saved["scores"]["realism"]["score"] == 4
    assert saved["scores"]["conversation_flow"]["score"] == 2
    assert saved["score_summary"]["needs_attention"][0]["id"] == "conversation_flow"


def test_evaluation_summary_lists_saved_reports(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VERBATIM_EVENT_LOG_PATH", str(tmp_path / "events.jsonl"))
    clear_settings_cache()
    client = TestClient(create_app())
    client.put("/api/evaluations/call/call_one", json={"bot_version": "v01", "scores": {"realism": 5}})
    client.put("/api/evaluations/call/call_two", json={"bot_version": "v02", "scores": {"realism": 3}})

    response = client.get("/api/evaluations/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["evaluation_count"] == 2
    assert payload["overall_average"] == 4.0
    assert [item["bot_version"] for item in payload["versions"]] == ["v01", "v02"]
    assert payload["versions"][0]["evaluation_count"] == 1


def test_evaluation_summary_averages_hundred_call_style_version_batches(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    settings = Settings.from_env({"VERBATIM_EVENT_LOG_PATH": str(tmp_path / "data" / "events.jsonl")})
    for index in range(3):
        save_call_evaluation(
            settings,
            [],
            call_id=f"call_v01_{index}",
            payload={"bot_version": "v01", "scores": {"realism": 5, "tool_calling": 4}},
        )
    for index in range(2):
        save_call_evaluation(
            settings,
            [],
            call_id=f"call_v02_{index}",
            payload={"bot_version": "v02", "scores": {"realism": 3, "tool_calling": 2}},
        )

    summary = summarize_evaluations(settings, [])

    versions = {item["bot_version"]: item for item in summary["versions"]}
    assert versions["v01"]["evaluation_count"] == 3
    assert versions["v01"]["overall_average"] == 4.5
    assert versions["v01"]["domain_averages"]["realism"] == 5.0
    assert versions["v02"]["evaluation_count"] == 2
    assert versions["v02"]["domain_averages"]["tool_calling"] == 2.0


def event(call_id, turn_id, name, timestamp):
    return {
        "schema_version": "verbatim.v2",
        "session_id": "sess",
        "call_id": call_id,
        "turn_id": turn_id,
        "agent_id": "agent",
        "client_id": "client",
        "event_name": name,
        "timestamp_wall_iso": "2026-01-01T00:00:00+00:00",
        "timestamp_monotonic_ms": timestamp,
        "provider": "test",
        "metadata": {},
    }
