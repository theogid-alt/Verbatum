import unittest

from verbatim.pipeline.first_phrase import FirstPhraseTextAggregator
from verbatim.pipeline.pipecat_processors import create_fast_ack_processor


class FakeRecorder:
    def __init__(self):
        self.sent = []

    def handle_first_speakable_phrase_sent(self, text, *, reason):
        self.sent.append((text, reason))


class FirstPhraseTextAggregatorTests(unittest.IsolatedAsyncioTestCase):
    def test_fast_ack_processor_factory_returns_processor(self):
        processor = create_fast_ack_processor(
            "test-fast-ack",
            recorder=FakeRecorder(),
            enabled=False,
            timeout_ms=350,
            text="Sure.",
        )

        self.assertIsNotNone(processor)
        self.assertTrue(hasattr(processor, "process_frame"))

    async def test_flushes_first_phrase_on_punctuation(self):
        recorder = FakeRecorder()
        aggregator = FirstPhraseTextAggregator(
            recorder=recorder,
            timeout_ms=0,
            min_words=2,
            max_words=6,
            after_first_mode="sentence",
        )

        output = [item async for item in aggregator.aggregate("Okay, I can help. The rest")]

        self.assertEqual(output[0].text, "Okay, I can help.")
        self.assertEqual(output[0].type, "first_phrase")
        self.assertEqual(recorder.sent[0], ("Okay, I can help.", "punctuation"))

    async def test_timeout_flushes_complete_words_without_partial_word(self):
        recorder = FakeRecorder()
        aggregator = FirstPhraseTextAggregator(
            recorder=recorder,
            timeout_ms=0,
            min_words=2,
            max_words=3,
            after_first_mode="sentence",
        )

        output = [item async for item in aggregator.aggregate("Okay I can help")]

        self.assertEqual(output[0].text, "Okay I can")
        self.assertEqual(output[0].type, "first_phrase")
        self.assertEqual(recorder.sent[0], ("Okay I can", "timeout"))


if __name__ == "__main__":
    unittest.main()
