from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from verbatim.config import InstrumentationConfig
from verbatim.events import EventLogger, normalize_event_name


class EventLoggerTests(unittest.TestCase):
    def test_normalizes_tts_typo(self):
        self.assertEqual(normalize_event_name("atts.request_started"), "tts.request_started")

    def test_writes_jsonl_event(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "events.jsonl"
            logger = EventLogger(
                InstrumentationConfig(event_log_path=path),
                session_id="sess_1",
                call_id="call_1",
                agent_id="agent",
                client_id="client",
            )
            event = logger.emit("llm.first_token", turn_id="turn_0001", provider="gemini")
            logger.flush()
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["event_name"], "llm.first_token")
            self.assertEqual(rows[0]["provider"], "gemini")
            self.assertEqual(event.turn_id, "turn_0001")
            logger.close()


if __name__ == "__main__":
    unittest.main()
