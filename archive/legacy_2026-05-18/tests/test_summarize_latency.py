from pathlib import Path
import json
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


class SummarizeLatencyScriptTests(unittest.TestCase):
    def test_script_reports_slow_turn(self):
        with TemporaryDirectory() as temp_dir:
            events_path = Path(temp_dir) / "events.jsonl"
            rows = [
                event("user.speech_stopped", 1000),
                event("turn.user_committed", 1100),
                event("llm.request_started", 1110),
                event("llm.first_token", 2500),
                event("tts.request_started", 2520),
                event("tts.first_audio_chunk", 2600),
                event("assistant.playback_started", 3200),
                event("turn.completed", 4000),
            ]
            events_path.write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/summarize_latency.py",
                    "--events",
                    str(events_path),
                    "--call-id",
                    "call_1",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("Turns above 2000 ms", result.stdout)
            self.assertIn("turn_0001", result.stdout)


def event(name, timestamp):
    return {
        "schema_version": "0.1",
        "session_id": "sess_1",
        "call_id": "call_1",
        "turn_id": "turn_0001",
        "agent_id": "agent",
        "client_id": "client",
        "event_name": name,
        "timestamp_wall_iso": "2026-05-10T00:00:00+00:00",
        "timestamp_monotonic_ms": timestamp,
        "provider": None,
        "metadata": {},
    }


if __name__ == "__main__":
    unittest.main()

