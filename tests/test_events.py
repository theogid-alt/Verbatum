from verbatim.analytics.call_notes import generate_call_notes
from verbatim.analytics.latency import summarize_call_events
from verbatim.events import EventSink, load_events


def test_event_sink_writes_schema_and_redacts(tmp_path):
    sink = EventSink(
        tmp_path / "events.jsonl",
        tmp_path / "transcripts",
        tmp_path / "calls",
        session_id="sess",
        call_id="call",
        agent_id="agent",
        client_id="client",
    )
    sink.emit("Secret Event", metadata={"api_key": "secret", "safe": "ok"})
    [event] = load_events(tmp_path / "events.jsonl")
    assert event["schema_version"] == "verbatim.v2"
    assert event["event_name"] == "secret.event"
    assert event["metadata"]["api_key"] == "[redacted]"
    assert event["metadata"]["safe"] == "ok"


def test_latency_summary_isolated_by_call_id():
    events = [
        event("call_a", "turn_0001", "transcript.user", 1000),
        event("call_a", "turn_0001", "llm.request_started", 1010),
        event("call_a", "turn_0001", "llm.first_token", 1110),
        event("call_a", "turn_0001", "tts.request_started", 1120),
        event("call_a", "turn_0001", "tts.first_audio", 1320),
        event("call_a", "turn_0001", "assistant.playback_started", 1350),
        event("call_b", "turn_0001", "transcript.user", 1000),
        event("call_b", "turn_0001", "assistant.playback_started", 9000),
    ]
    summary = summarize_call_events(events, call_id="call_a")
    assert summary["turn_count"] == 1
    assert summary["avg_perceived_latency_ms"] == 350
    assert summary["avg_provider_ttft_ms"] == 100
    assert summary["avg_tts_first_audio_ms"] == 200


def test_latency_summary_accepts_v2_dotted_event_names():
    events = [
        event("call_a", "turn_0001", "transcript.user", 1000),
        event("call_a", "turn_0001", "llm.request.started", 1010),
        event("call_a", "turn_0001", "llm.first.token", 1110),
        event("call_a", "turn_0001", "tts.request.started", 1120),
        event("call_a", "turn_0001", "tts.first.audio", 1320),
        event("call_a", "turn_0001", "assistant.playback.started", 1350),
    ]

    summary = summarize_call_events(events, call_id="call_a")

    assert summary["avg_perceived_latency_ms"] == 350
    assert summary["avg_provider_ttft_ms"] == 100
    assert summary["avg_tts_first_audio_ms"] == 200
    assert summary["avg_playback_delay_ms"] == 30


def test_latency_summary_calculates_stt_processing_from_speech_stop_metadata():
    transcript = event("call_a", "turn_0001", "transcript.user", 1000)
    transcript["metadata"] = {
        "text": "Hello",
        "user_speech_started_at_ms": 700,
        "user_speech_stopped_at_ms": 880,
    }
    events = [
        transcript,
        event("call_a", "turn_0001", "assistant.playback.started", 1300),
    ]

    summary = summarize_call_events(events, call_id="call_a")

    assert summary["avg_stt_processing_ms"] == 120
    assert summary["avg_speech_to_transcript_ms"] == 300
    assert summary["avg_perceived_latency_ms"] == 300


def test_latency_summary_prefers_transcript_stt_processing_metadata():
    transcript = event("call_a", "turn_0001", "transcript.user", 1000)
    transcript["metadata"] = {
        "text": "Hello",
        "stt_processing_ms": 180.4,
        "user_speech_stopped_at_ms": 880,
    }
    events = [
        transcript,
        event("call_a", "turn_0001", "user.speech.stopped", 3000),
    ]

    summary = summarize_call_events(events, call_id="call_a")

    assert summary["avg_stt_processing_ms"] == 180.4


def test_latency_summary_counts_direct_tool_actions_as_tool_calls():
    tool = event("call_a", "turn_0001", "tool.direct.activated", 1000)
    tool["metadata"] = {"tool_name": "check_calendar_conflict", "outcome": "started"}

    summary = summarize_call_events([tool], call_id="call_a")

    assert summary["tool_call_count"] == 1
    assert summary["tool_event_counts"]["tool.direct.activated"] == 1


def test_call_notes_are_generated_from_transcript_and_tool_events():
    user = event("call_a", "turn_0001", "transcript.user", 1000)
    user["metadata"] = {"text": "Can you book Friday at 2?"}
    assistant = event("call_a", "turn_0001", "transcript.assistant", 1200)
    assistant["metadata"] = {"text": "Yes, I booked it and can text a confirmation."}
    tool = event("call_a", "turn_0001", "tool.call.completed", 1100)
    tool["metadata"] = {"tool_name": "confirm_calendar_booking", "outcome": "booking_confirmed", "duration_ms": 220}
    ended = event("call_a", None, "session.ended", 1500)
    ended["metadata"] = {"outcome": "completed"}

    notes = generate_call_notes([user, assistant, tool, ended], call_id="call_a")

    assert notes["status"] == "ready"
    assert notes["outcome"] == "completed"
    assert notes["user_turns"] == 1
    assert "Transcript highlights" not in notes["notes_text"]
    assert "Calendar booking succeeded" in notes["notes_text"]


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
