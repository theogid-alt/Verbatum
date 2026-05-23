import unittest

from verbatim.analytics.latency import compute_turn_latency, percentile, summarize_call_events


class LatencyTests(unittest.TestCase):
    def test_percentile_uses_nearest_rank(self):
        self.assertEqual(percentile([100, 200, 300, 400], 50), 200)
        self.assertEqual(percentile([100, 200, 300, 400], 95), 400)

    def test_compute_turn_latency(self):
        events = [
            event("user.speech_stopped", 1000),
            event("stt.eager_end_of_turn", 1080),
            event("stt.utterance_end", 1110),
            event("stt.final_transcript", 1125),
            event("turn.user_committed", 1125),
            event("transcript.ready", 1125),
            event("llm.enqueued", 1130),
            event("llm.request_started", 1150),
            event("llm.provider_first_chunk", 1320),
            event("llm.first_raw_token", 1320),
            event("llm.first_token", 1320),
            event("llm.raw_token", 1320),
            event("llm.raw_token", 1360),
            event("llm.time_to_3_words", 1360),
            event("llm.time_to_6_words", 1390),
            event("llm.first_speakable_phrase", 1321),
            event("llm.first_text_frame_emitted", 1321),
            event("llm.first_text_chunk", 1321),
            event("tts.first_text_sent", 1321),
            event("tts.first_speakable_phrase_sent", 1330),
            event("tts.first_text_received", 1340),
            event("tts.request_started", 1340),
            event("tts.first_audio_chunk", 1440),
            event("assistant.playback_started", 1490),
            event("assistant.speech_completed", 2600),
        ]
        latency = compute_turn_latency(events)
        self.assertEqual(latency["turn_detection_latency_ms"], 125)
        self.assertEqual(latency["stt_eager_eot_latency_ms"], 80)
        self.assertEqual(latency["stt_final_eot_latency_ms"], 110)
        self.assertEqual(latency["eager_to_final_gap_ms"], 30)
        self.assertEqual(latency["transcript_to_llm_enqueue_ms"], 5)
        self.assertEqual(latency["transcript_ready_to_llm_enqueue_ms"], 5)
        self.assertEqual(latency["llm_queue_latency_ms"], 20)
        self.assertEqual(latency["llm_provider_first_chunk_ms"], 170)
        self.assertEqual(latency["llm_provider_ttfb_ms"], 170)
        self.assertEqual(latency["first_token_to_3_words_ms"], 40)
        self.assertEqual(latency["first_token_to_6_words_ms"], 70)
        self.assertEqual(latency["first_token_to_speakable_phrase_ms"], 1)
        self.assertEqual(latency["max_inter_token_gap_ms"], 40)
        self.assertEqual(latency["llm_stream_gap_ms"], 40)
        self.assertEqual(latency["first_token_to_text_frame_ms"], 1)
        self.assertEqual(latency["text_frame_to_tts_input_ms"], 19)
        self.assertEqual(latency["first_speakable_phrase_to_tts_input_ms"], 19)
        self.assertEqual(latency["llm_ttft_total_ms"], 196)
        self.assertEqual(latency["llm_ttfb_ms"], 170)
        self.assertEqual(latency["first_text_to_tts_latency_ms"], 215)
        self.assertEqual(latency["tts_ttfb_ms"], 100)
        self.assertEqual(latency["speakable_phrase_to_tts_audio_ms"], 119)
        self.assertEqual(latency["playback_latency_ms"], 50)
        self.assertEqual(latency["perceived_response_latency_ms"], 490)
        self.assertEqual(latency["transcript_ready_to_playback_ms"], 365)
        self.assertEqual(latency["full_turn_duration_ms"], 1600)

    def test_summarize_call_flags_failed_and_interrupted(self):
        events = [
            event("user.speech_stopped", 1000, turn_id="turn_0001"),
            event("assistant.playback_started", 1700, turn_id="turn_0001"),
            event("turn.completed", 2500, turn_id="turn_0001"),
            event("turn.failed", 3000, turn_id="turn_0002", provider="gemini"),
            event("llm.error", 3001, turn_id="turn_0002", provider="gemini"),
            event("turn.interrupted", 4000, turn_id="turn_0003"),
        ]
        summary = summarize_call_events(events, call_id="call_1")
        self.assertEqual(summary["total_turns"], 3)
        self.assertEqual(summary["successful_turns"], 1)
        self.assertEqual(summary["failed_turns"], 1)
        self.assertEqual(summary["interrupted_turns"], 1)
        self.assertEqual(summary["error_count_by_provider"], {"gemini": 1})

    def test_summarize_call_adds_bottleneck_and_eager_counts(self):
        events = [
            event(
                "session.configured",
                900,
                turn_id=None,
                metadata={"llm_provider": "openai", "llm_model": "gpt-4o-mini"},
            ),
            event("user.speech_stopped", 1000),
            event("stt.eager_end_of_turn", 1200),
            event("stt.turn_resumed", 1210),
            event("turn.eager_cancelled", 1211),
            event("stt.utterance_end", 1500),
            event("stt.final_transcript", 1500),
            event("turn.user_committed", 1501),
            event("transcript.ready", 1501),
            event(
                "llm.enqueued",
                1501,
                metadata={
                    "llm_started_reason": "final",
                    "llm_provider": "openai",
                    "llm_model": "gpt-4o-mini",
                },
            ),
            event("llm.request_started", 1502),
            event("llm.first_raw_token", 1700),
            event("llm.first_text_frame_emitted", 1700),
            event("tts.first_text_received", 1720),
            event("tts.request_started", 1720),
            event("tts.first_audio_chunk", 1820),
            event("assistant.playback_started", 1900),
        ]
        summary = summarize_call_events(events, call_id="call_1")
        turn = summary["turns"][0]
        self.assertEqual(summary["turn_resumed_count"], 1)
        self.assertEqual(summary["eager_cancel_count"], 1)
        self.assertEqual(summary["llm_provider"], "openai")
        self.assertEqual(summary["llm_model"], "gpt-4o-mini")
        self.assertEqual(summary["llm_started_on_counts"], {"final": 1})
        self.assertEqual(summary["avg_transcript_ready_to_playback_ms"], 399)
        self.assertEqual(summary["p95_transcript_ready_to_playback_ms"], 399)
        self.assertEqual(turn["dominant_bottleneck"], "turn_detection")
        self.assertEqual(turn["llm_started_on"], "final")
        self.assertEqual(turn["llm_provider"], "openai")
        self.assertEqual(turn["llm_model"], "gpt-4o-mini")
        self.assertIn("stt_eager_eot_at", turn["timestamps"])

    def test_barge_in_stale_llm_classifies_as_stale_bottleneck(self):
        events = [
            event("user.speech_stopped", 1000),
            event("transcript.ready", 1000),
            event("llm.enqueued", 1001),
            event("llm.request_started", 1002),
            event("barge_in.before_audio", 1050),
            event("llm.active_cancelled", 1051),
            event("llm.stale_completed", 1800),
            event("turn.interrupted", 1801),
        ]

        summary = summarize_call_events(events, call_id="call_1")
        turn = summary["turns"][0]
        self.assertEqual(turn["dominant_bottleneck"], "interruption_recovery")
        self.assertTrue(turn["active_llm_cancelled"])
        self.assertTrue(turn["barge_in_before_audio"])
        self.assertTrue(turn["stale_llm_completed"])

    def test_summarize_call_isolates_metrics_by_call_id(self):
        events = [
            event("user.speech_stopped", 1000, turn_id="turn_0001"),
            event("assistant.playback_started", 1500, turn_id="turn_0001"),
            {
                **event("user.speech_stopped", 1000, turn_id="turn_0001"),
                "call_id": "call_2",
            },
            {
                **event("assistant.playback_started", 9000, turn_id="turn_0001"),
                "call_id": "call_2",
            },
        ]

        summary = summarize_call_events(events, call_id="call_1")
        self.assertEqual(summary["total_turns"], 1)
        self.assertEqual(summary["avg_perceived_latency_ms"], 500)

    def test_summarize_call_counts_echo_suppression_events(self):
        events = [
            event("user.speech_stopped", 1000),
            event("audio.echo_suppressed", 1100, metadata={"frame_type": "InterimTranscriptionFrame"}),
            {
                **event(
                    "audio.echo_suppressed",
                    1200,
                    metadata={"frame_type": "InterimTranscriptionFrame"},
                ),
                "call_id": "call_2",
            },
        ]

        summary = summarize_call_events(events, call_id="call_1")
        self.assertEqual(summary["echo_suppressed_count"], 1)

    def test_summarize_call_counts_conversation_quality_events(self):
        events = [
            event("conversation.mode", 1000, metadata={"conversation_mode": "social"}),
            event("assistant.form_pattern_detected", 1010),
            event("assistant.style_guard_rewritten", 1020),
            event("barge_in.valid", 1030),
            event("barge_in.false", 1040),
            event("turn.premature_assistant_start", 1050),
            event("turn.user_utterance_split", 1060),
            event("voice.cutout_suspected", 1070),
            event(
                "assistant.interrupted",
                1080,
                metadata={"assistant_speech_cancelled_reason": "hard_interrupt_phrase"},
            ),
        ]

        summary = summarize_call_events(events, call_id="call_1")
        turn = summary["turns"][0]
        self.assertEqual(summary["conversation_mode_counts"], {"social": 1})
        self.assertEqual(summary["valid_barge_in_count"], 1)
        self.assertEqual(summary["false_barge_in_count"], 1)
        self.assertEqual(summary["premature_assistant_start_count"], 1)
        self.assertEqual(summary["user_utterance_split_count"], 1)
        self.assertEqual(summary["voice_cutout_suspected_count"], 1)
        self.assertEqual(summary["form_pattern_failure_count"], 1)
        self.assertEqual(summary["style_guard_rewrite_count"], 1)
        self.assertEqual(turn["conversation_mode"], "social")
        self.assertTrue(turn["voice_cutout_suspected"])
        self.assertEqual(turn["assistant_speech_cancelled_reason"], "hard_interrupt_phrase")

    def test_ultravox_summary_uses_response_metric_for_display_latency(self):
        events = [
            event(
                "session.configured",
                900,
                turn_id=None,
                metadata={"llm_provider": "ultravox", "llm_model": "fixie-ai/ultravox"},
            ),
            event("ultravox.transcript.user", 900, turn_id=None, provider="ultravox"),
            event("transcript.ready", 1000, turn_id="turn_0001", provider="ultravox"),
            event("assistant.playback_started", 1500, turn_id="turn_0001", provider="ultravox"),
            event(
                "metrics.observed",
                1110,
                turn_id="turn_0001",
                provider="ultravox",
                metadata={"metric_type": "ProcessingMetricsData", "value": "0.8"},
            ),
            event("ultravox.transcript.user", 1800, turn_id=None, provider="ultravox"),
            event("transcript.ready", 2000, turn_id="turn_0002", provider="ultravox"),
            event("assistant.playback_started", 1850, turn_id="turn_0002", provider="ultravox"),
            event(
                "metrics.observed",
                2020,
                turn_id="turn_0002",
                provider="ultravox",
                metadata={"metric_type": "ProcessingMetricsData", "value": "1.2"},
            ),
        ]

        summary = summarize_call_events(events, call_id="call_1")

        self.assertEqual(summary["perceived_latency_source"], "ultravox_user_final_to_playback")
        self.assertEqual(summary["avg_perceived_latency_ms"], 600)
        self.assertEqual(summary["p95_perceived_latency_ms"], 600)
        self.assertEqual(summary["real_p95_ms"], 600)
        self.assertEqual(summary["avg_ultravox_response_latency_ms"], 600)
        self.assertEqual(summary["avg_ultravox_processing_latency_ms"], 1000)
        self.assertEqual(
            summary["turns"][0]["latency"]["ultravox_response_latency_ms"],
            600,
        )

    def test_hume_summary_dedupes_user_messages_and_uses_first_playback(self):
        events = [
            event(
                "session.configured",
                900,
                turn_id=None,
                provider="hume_evi",
                metadata={
                    "transport_provider": "hume_evi",
                    "llm_provider": "hume_evi",
                    "llm_model": "hume-evi",
                },
            ),
            event(
                "hume.client.user_message",
                1000,
                turn_id=None,
                provider="browser",
                metadata={"transcript": "I saw a property in Dubai Creek."},
            ),
            event(
                "hume.client.user_message",
                1200,
                turn_id=None,
                provider="browser",
                metadata={"transcript": "I saw a property in Dubai Creek."},
            ),
            event("hume.client.first_audio_output", 1500, turn_id=None, provider="browser"),
            event("hume.client.first_audio_playing", 1650, turn_id=None, provider="browser"),
            event(
                "hume.client.assistant_message",
                1660,
                turn_id=None,
                provider="browser",
                metadata={"transcript": "Hold on one second, let me check."},
            ),
            event(
                "hume.client.user_message",
                3000,
                turn_id=None,
                provider="browser",
                metadata={"transcript": "End the call."},
            ),
            event("hume.client.first_audio_playing", 3450, turn_id=None, provider="browser"),
        ]

        summary = summarize_call_events(events, call_id="call_1")

        self.assertEqual(summary["perceived_latency_source"], "hume_user_message_to_first_audio_playing")
        self.assertEqual(summary["total_turns"], 2)
        self.assertEqual(summary["avg_hume_first_audio_output_ms"], 500)
        self.assertEqual(summary["avg_hume_first_audio_playing_ms"], 550)
        self.assertEqual(summary["p95_hume_first_audio_playing_ms"], 650)
        self.assertEqual(summary["avg_hume_audio_output_to_playback_ms"], 150)
        self.assertEqual(summary["turns"][0]["latency"]["hume_first_audio_playing_ms"], 650)


def event(name, timestamp, turn_id="turn_0001", provider=None, metadata=None):
    return {
        "schema_version": "0.1",
        "session_id": "sess_1",
        "call_id": "call_1",
        "turn_id": turn_id,
        "agent_id": "agent",
        "client_id": "client",
        "event_name": name,
        "timestamp_wall_iso": "2026-05-10T00:00:00+00:00",
        "timestamp_monotonic_ms": timestamp,
        "provider": provider,
        "metadata": metadata or {},
    }


if __name__ == "__main__":
    unittest.main()
