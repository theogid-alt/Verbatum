from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from verbatim.config import InstrumentationConfig
from verbatim.events import EventLogger
from verbatim.instrumentation.recorder import CallRecorder


class UserStartedSpeakingFrame:
    pass


class InterimTranscriptionFrame:
    text = "echoed assistant words"


class TranscriptionFrame:
    text = "wait, let me finish"


class LLMFullResponseStartFrame:
    pass


class TTSAudioRawFrame:
    pass


class BotStartedSpeakingFrame:
    pass


class RecorderTests(unittest.TestCase):
    def test_assistant_output_frame_does_not_create_phantom_turn(self):
        with recorder_fixture() as recorder:
            recorder.ensure_turn()
            recorder.complete_turn("success")

            recorder.handle_frame(TTSAudioRawFrame(), stage="verbatim-output-events")

            self.assertEqual(recorder.turn_index, 1)
            self.assertIsNone(recorder.current_turn_id)
            self.assertTrue(
                any(event["event_name"] == "turn.phantom_prevented" for event in recorder.events)
            )

    def test_user_speech_cancels_in_flight_llm_before_audio(self):
        with recorder_fixture() as recorder:
            recorder.ensure_turn()
            recorder.handle_frame(LLMFullResponseStartFrame(), stage="verbatim-pre-llm-events")

            recorder.handle_frame(UserStartedSpeakingFrame(), stage="verbatim-input-events")

            names = [event["event_name"] for event in recorder.events]
            self.assertIn("llm.active_cancelled", names)
            self.assertIn("barge_in.before_audio", names)
            self.assertEqual(
                recorder.consume_pending_pipeline_interrupt(),
                "user_continued_before_audio",
            )
            self.assertEqual(recorder.current_turn_id, "turn_0002")

    def test_tiered_barge_in_marks_early_noise_without_cancelling(self):
        with recorder_fixture() as recorder:
            recorder.ensure_turn()
            llm_start = LLMFullResponseStartFrame()
            tts_audio = TTSAudioRawFrame()
            bot_started = BotStartedSpeakingFrame()
            recorder.handle_frame(llm_start, stage="verbatim-pre-llm-events")
            recorder.handle_frame(tts_audio, stage="verbatim-tts-events")
            recorder.handle_frame(bot_started, stage="verbatim-output-events")

            frame = UserStartedSpeakingFrame()
            recorder.handle_frame(frame, stage="verbatim-input-events")

            names = [event["event_name"] for event in recorder.events]
            self.assertIn("barge_in.possible", names)
            self.assertIn("barge_in.false", names)
            self.assertNotIn("llm.active_cancelled", names)
            self.assertTrue(recorder.should_drop_frame(frame, stage="verbatim-input-events"))

    def test_hard_interrupt_phrase_cancels_during_assistant_speech(self):
        with recorder_fixture() as recorder:
            recorder.ensure_turn()
            llm_start = LLMFullResponseStartFrame()
            tts_audio = TTSAudioRawFrame()
            bot_started = BotStartedSpeakingFrame()
            recorder.handle_frame(llm_start, stage="verbatim-pre-llm-events")
            recorder.handle_frame(tts_audio, stage="verbatim-tts-events")
            recorder.handle_frame(bot_started, stage="verbatim-output-events")

            recorder.handle_frame(
                TranscriptionFrame(),
                stage="verbatim-stt-events",
            )

            names = [event["event_name"] for event in recorder.events]
            self.assertIn("barge_in.valid", names)
            self.assertIn("voice.cutout_suspected", names)
            self.assertIn("llm.active_cancelled", names)

    def test_echo_suppression_drops_user_frames_while_assistant_speaks(self):
        with recorder_fixture() as recorder:
            recorder.ensure_turn()
            recorder.handle_frame(BotStartedSpeakingFrame(), stage="verbatim-output-events")

            frame = InterimTranscriptionFrame()
            self.assertTrue(recorder.should_suppress_user_echo(frame, echo_suppression_ms=900))
            recorder.handle_echo_suppressed(frame, stage="verbatim-stt-events")

            event = recorder.events[-1]
            self.assertEqual(event["event_name"], "audio.echo_suppressed")
            self.assertEqual(event["metadata"]["frame_type"], "InterimTranscriptionFrame")
            self.assertEqual(event["metadata"]["stage"], "verbatim-stt-events")

    def test_provider_final_assistant_transcript_overrides_delta_chunks(self):
        with recorder_fixture() as recorder:
            recorder.set_llm_provider("ultravox", "fixie-ai/ultravox")
            turn_id = recorder.ensure_turn()
            recorder.handle_assistant_final_transcript("Clean final answer.")

            recorder.handle_assistant_turn_stopped("Clean Clean final answer.", metadata={})
            recorder.logger.flush()

            transcript_path = recorder.logger.config.transcript_dir / "call_1.jsonl"
            rows = [
                json.loads(line)
                for line in transcript_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(rows[-1]["role"], "assistant")
            self.assertEqual(rows[-1]["turn_id"], turn_id)
            self.assertEqual(rows[-1]["text"], "Clean final answer.")


class recorder_fixture:
    def __enter__(self):
        self.temp_dir = TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.logger = EventLogger(
            InstrumentationConfig(
                enable_jsonl_events=False,
                event_log_path=root / "events.jsonl",
                call_summary_dir=root / "calls",
                transcript_dir=root / "transcripts",
            ),
            session_id="sess_1",
            call_id="call_1",
            agent_id="agent",
            client_id="client",
        )
        self.recorder = CallRecorder(self.logger)
        return self.recorder

    def __exit__(self, exc_type, exc, tb):
        self.logger.close()
        self.temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
