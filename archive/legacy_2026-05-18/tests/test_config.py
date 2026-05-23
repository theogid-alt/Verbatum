import unittest

from verbatim.config import Settings


class SettingsTests(unittest.TestCase):
    def test_missing_agent_keys_lists_required_values(self):
        settings = Settings.from_env({})
        self.assertEqual(settings.providers.stt_provider, "deepgram")
        self.assertEqual(settings.providers.deepgram_model, "nova-3-general")
        self.assertEqual(settings.session.llm_history_messages, 1)
        self.assertEqual(settings.session.user_turn_stop_timeout, 5.0)
        self.assertTrue(settings.session.latency_diagnostic_mode)
        self.assertTrue(settings.session.final_transcript_eager_commit)
        self.assertEqual(settings.session.final_transcript_commit_delay_ms, 0)
        self.assertFalse(settings.session.final_transcript_require_complete_utterance)
        self.assertEqual(settings.session.final_transcript_fragment_delay_ms, 220)
        self.assertTrue(settings.session.response_style_guard_enabled)
        self.assertTrue(settings.session.vad_only_user_turn_start)
        self.assertFalse(settings.session.mute_user_while_bot_speaking)
        self.assertTrue(settings.session.llm_prewarm_enabled)
        self.assertIn("Never say you are an AI", settings.prompt.system_prompt)
        self.assertEqual(settings.prompt.max_tokens, 32)
        self.assertEqual(settings.voice.tts_text_aggregation_mode, "sentence")
        self.assertFalse(settings.voice.tts_first_phrase_flush_enabled)
        self.assertEqual(settings.voice.tts_first_flush_timeout_ms, 150)
        self.assertEqual(settings.voice.tts_first_flush_min_words, 2)
        self.assertEqual(settings.voice.tts_first_flush_max_words, 6)
        self.assertEqual(settings.voice.tts_after_first_mode, "sentence")
        self.assertIsNone(settings.voice.cartesia_max_buffer_delay_ms)
        self.assertFalse(settings.session.fast_ack_enabled)
        self.assertEqual(settings.session.fast_ack_timeout_ms, 350)
        self.assertEqual(settings.session.assistant_min_speak_ms_before_barge_in, 400)
        self.assertEqual(settings.session.barge_in_min_speech_ms, 300)
        self.assertEqual(settings.session.barge_in_min_transcript_words, 2)
        self.assertEqual(
            settings.session.hard_interrupt_phrases,
            "stop,wait,hold on,let me finish,actually,no",
        )
        self.assertEqual(settings.session.utterance_split_window_ms, 1200)
        self.assertEqual(settings.session.user_resume_after_assistant_window_ms, 800)
        self.assertEqual(settings.providers.llm_provider, "gemini")
        self.assertEqual(settings.providers.llm_model, "gemini-2.5-flash")
        self.assertEqual(settings.providers.transport_provider, "daily")
        self.assertIsNone(settings.providers.daily_geo)
        self.assertFalse(settings.providers.daily_force_create_room)
        self.assertIsNone(settings.providers.livekit_audio_in_sample_rate)
        self.assertIsNone(settings.providers.livekit_audio_out_sample_rate)
        self.assertEqual(settings.providers.livekit_audio_out_bitrate, 96000)
        self.assertEqual(settings.providers.livekit_audio_out_10ms_chunks, 4)
        self.assertTrue(settings.providers.livekit_audio_out_auto_silence)
        self.assertTrue(settings.providers.livekit_browser_echo_cancellation)
        self.assertTrue(settings.providers.livekit_browser_noise_suppression)
        self.assertTrue(settings.providers.livekit_browser_auto_gain_control)
        self.assertEqual(settings.providers.livekit_browser_audio_sample_rate, 48000)
        self.assertIsNone(settings.providers.ultravox_turn_endpoint_delay_seconds)
        self.assertIsNone(settings.providers.ultravox_minimum_turn_duration_seconds)
        self.assertIsNone(settings.providers.ultravox_minimum_interruption_duration_seconds)
        self.assertIsNone(settings.providers.ultravox_frame_activation_threshold)
        self.assertIsNone(settings.providers.ultravox_client_buffer_size_ms)
        self.assertIsNone(settings.providers.ultravox_media_idle_timeout_seconds)
        self.assertEqual(settings.prompt.temperature, 0.0)
        self.assertEqual(settings.session.echo_suppression_ms, 0)
        self.assertEqual(
            settings.missing_agent_keys(),
            [
                "DAILY_API_KEY",
                "DEEPGRAM_API_KEY",
                "CARTESIA_API_KEY",
                "VERBATIM_CARTESIA_VOICE_ID",
                "GOOGLE_API_KEY",
            ],
        )

    def test_env_loads_nested_config(self):
        settings = Settings.from_env(
            {
                "DAILY_API_KEY": "daily",
                "DAILY_GEO": "eu-central-1",
                "VERBATIM_DAILY_FORCE_CREATE_ROOM": "true",
                "DEEPGRAM_API_KEY": "deepgram",
                "GOOGLE_API_KEY": "google",
                "OPENAI_API_KEY": "openai",
                "GROQ_API_KEY": "groq",
                "QWEN_API_KEY": "qwen",
                "XAI_API_KEY": "xai",
                "ULTRAVOX_API_KEY": "ultravox",
                "HUME_API_KEY": "hume",
                "HUME_SECRET_KEY": "hume-secret",
                "HUME_EVI_CONFIG_ID": "11111111-1111-1111-1111-111111111111",
                "HUME_EVI_CONFIG_VERSION": "2",
                "HUME_EVI_VOICE_ID": "22222222-2222-2222-2222-222222222222",
                "HUME_EVI_VERBOSE_TRANSCRIPTION": "false",
                "HUME_EVI_SEND_SYSTEM_PROMPT": "false",
                "HUME_EVI_SYSTEM_PROMPT": "Hume Alicia prompt",
                "CARTESIA_API_KEY": "cartesia",
                "LIVEKIT_URL": "wss://example.livekit.cloud",
                "LIVEKIT_API_KEY": "livekit-key",
                "LIVEKIT_API_SECRET": "livekit-secret",
                "VERBATIM_LIVEKIT_AUDIO_IN_SAMPLE_RATE": "48000",
                "VERBATIM_LIVEKIT_AUDIO_OUT_SAMPLE_RATE": "48000",
                "VERBATIM_LIVEKIT_AUDIO_OUT_BITRATE": "64000",
                "VERBATIM_LIVEKIT_AUDIO_OUT_10MS_CHUNKS": "2",
                "VERBATIM_LIVEKIT_AUDIO_OUT_AUTO_SILENCE": "false",
                "VERBATIM_LIVEKIT_BROWSER_ECHO_CANCELLATION": "false",
                "VERBATIM_LIVEKIT_BROWSER_NOISE_SUPPRESSION": "false",
                "VERBATIM_LIVEKIT_BROWSER_AUTO_GAIN_CONTROL": "false",
                "VERBATIM_LIVEKIT_BROWSER_AUDIO_SAMPLE_RATE": "44100",
                "VERBATIM_CARTESIA_VOICE_ID": "voice",
                "VERBATIM_AGENT_ID": "agent_custom",
                "VERBATIM_CLIENT_ID": "client_custom",
                "VERBATIM_STT_PROVIDER": "deepgram_flux",
                "VERBATIM_TTS_TEXT_AGGREGATION_MODE": "token",
                "VERBATIM_LLM_TEMPERATURE": "0.2",
                "VERBATIM_FINAL_TRANSCRIPT_EAGER_COMMIT": "false",
                "VERBATIM_FINAL_TRANSCRIPT_COMMIT_DELAY_MS": "220",
                "VERBATIM_FINAL_TRANSCRIPT_REQUIRE_COMPLETE_UTTERANCE": "true",
                "VERBATIM_FINAL_TRANSCRIPT_FRAGMENT_DELAY_MS": "180",
                "VERBATIM_RESPONSE_STYLE_GUARD_ENABLED": "false",
                "VERBATIM_VAD_ONLY_USER_TURN_START": "false",
                "VERBATIM_MUTE_USER_WHILE_BOT_SPEAKING": "true",
                "VERBATIM_LLM_PREWARM": "false",
                "VERBATIM_ECHO_SUPPRESSION_MS": "1200",
                "VERBATIM_TTS_FIRST_PHRASE_FLUSH_ENABLED": "true",
                "VERBATIM_TTS_FIRST_FLUSH_TIMEOUT_MS": "120",
                "VERBATIM_TTS_FIRST_FLUSH_MIN_WORDS": "3",
                "VERBATIM_TTS_FIRST_FLUSH_MAX_WORDS": "5",
                "VERBATIM_TTS_AFTER_FIRST_MODE": "token",
                "VERBATIM_CARTESIA_MAX_BUFFER_DELAY_MS": "100",
                "VERBATIM_FAST_ACK_ENABLED": "true",
                "VERBATIM_FAST_ACK_TIMEOUT_MS": "300",
                "VERBATIM_ASSISTANT_MIN_SPEAK_MS_BEFORE_BARGE_IN": "450",
                "VERBATIM_BARGE_IN_MIN_SPEECH_MS": "325",
                "VERBATIM_BARGE_IN_MIN_TRANSCRIPT_WORDS": "3",
                "VERBATIM_HARD_INTERRUPT_PHRASES": "stop,wait,nope",
                "VERBATIM_UTTERANCE_SPLIT_WINDOW_MS": "1300",
                "VERBATIM_USER_RESUME_AFTER_ASSISTANT_WINDOW_MS": "900",
                "VERBATIM_ULTRAVOX_MODEL": "fixie-ai/ultravox-test",
                "VERBATIM_ULTRAVOX_VOICE_ID": "00000000-0000-0000-0000-000000000000",
                "VERBATIM_ULTRAVOX_MAX_DURATION_SECONDS": "600",
                "VERBATIM_ULTRAVOX_TURN_ENDPOINT_DELAY_SECONDS": "0.256",
                "VERBATIM_ULTRAVOX_MINIMUM_TURN_DURATION_SECONDS": "0.064",
                "VERBATIM_ULTRAVOX_MINIMUM_INTERRUPTION_DURATION_SECONDS": "0.16",
                "VERBATIM_ULTRAVOX_FRAME_ACTIVATION_THRESHOLD": "0.2",
                "VERBATIM_ULTRAVOX_CLIENT_BUFFER_SIZE_MS": "40",
                "VERBATIM_ULTRAVOX_MEDIA_IDLE_TIMEOUT_SECONDS": "20",
            }
        )
        self.assertEqual(settings.agent.agent_id, "agent_custom")
        self.assertEqual(settings.agent.client_id, "client_custom")
        self.assertEqual(settings.providers.daily_geo, "eu-central-1")
        self.assertTrue(settings.providers.daily_force_create_room)
        self.assertEqual(settings.providers.stt_provider, "deepgram_flux")
        self.assertEqual(settings.voice.tts_text_aggregation_mode, "token")
        self.assertEqual(settings.prompt.temperature, 0.2)
        self.assertFalse(settings.session.final_transcript_eager_commit)
        self.assertEqual(settings.session.final_transcript_commit_delay_ms, 220)
        self.assertTrue(settings.session.final_transcript_require_complete_utterance)
        self.assertEqual(settings.session.final_transcript_fragment_delay_ms, 180)
        self.assertFalse(settings.session.response_style_guard_enabled)
        self.assertFalse(settings.session.vad_only_user_turn_start)
        self.assertTrue(settings.session.mute_user_while_bot_speaking)
        self.assertFalse(settings.session.llm_prewarm_enabled)
        self.assertEqual(settings.session.echo_suppression_ms, 1200)
        self.assertTrue(settings.voice.tts_first_phrase_flush_enabled)
        self.assertEqual(settings.voice.tts_first_flush_timeout_ms, 120)
        self.assertEqual(settings.voice.tts_first_flush_min_words, 3)
        self.assertEqual(settings.voice.tts_first_flush_max_words, 5)
        self.assertEqual(settings.voice.tts_after_first_mode, "token")
        self.assertEqual(settings.voice.cartesia_max_buffer_delay_ms, 100)
        self.assertTrue(settings.session.fast_ack_enabled)
        self.assertEqual(settings.session.fast_ack_timeout_ms, 300)
        self.assertEqual(settings.session.assistant_min_speak_ms_before_barge_in, 450)
        self.assertEqual(settings.session.barge_in_min_speech_ms, 325)
        self.assertEqual(settings.session.barge_in_min_transcript_words, 3)
        self.assertEqual(settings.session.hard_interrupt_phrases, "stop,wait,nope")
        self.assertEqual(settings.session.utterance_split_window_ms, 1300)
        self.assertEqual(settings.session.user_resume_after_assistant_window_ms, 900)
        self.assertEqual(settings.providers.ultravox_api_key, "ultravox")
        self.assertEqual(settings.providers.ultravox_model, "fixie-ai/ultravox-test")
        self.assertEqual(
            settings.providers.ultravox_voice_id,
            "00000000-0000-0000-0000-000000000000",
        )
        self.assertEqual(settings.providers.ultravox_max_duration_seconds, 600)
        self.assertEqual(settings.providers.livekit_audio_in_sample_rate, 48000)
        self.assertEqual(settings.providers.livekit_audio_out_sample_rate, 48000)
        self.assertEqual(settings.providers.livekit_audio_out_bitrate, 64000)
        self.assertEqual(settings.providers.livekit_audio_out_10ms_chunks, 2)
        self.assertFalse(settings.providers.livekit_audio_out_auto_silence)
        self.assertFalse(settings.providers.livekit_browser_echo_cancellation)
        self.assertFalse(settings.providers.livekit_browser_noise_suppression)
        self.assertFalse(settings.providers.livekit_browser_auto_gain_control)
        self.assertEqual(settings.providers.livekit_browser_audio_sample_rate, 44100)
        self.assertEqual(settings.providers.ultravox_turn_endpoint_delay_seconds, 0.256)
        self.assertEqual(settings.providers.ultravox_minimum_turn_duration_seconds, 0.064)
        self.assertEqual(
            settings.providers.ultravox_minimum_interruption_duration_seconds,
            0.16,
        )
        self.assertEqual(settings.providers.ultravox_frame_activation_threshold, 0.2)
        self.assertEqual(settings.providers.ultravox_client_buffer_size_ms, 40)
        self.assertEqual(settings.providers.ultravox_media_idle_timeout_seconds, 20)
        self.assertEqual(settings.providers.hume_api_key, "hume")
        self.assertEqual(settings.providers.hume_secret_key, "hume-secret")
        self.assertEqual(
            settings.providers.hume_evi_config_id,
            "11111111-1111-1111-1111-111111111111",
        )
        self.assertEqual(settings.providers.hume_evi_config_version, 2)
        self.assertEqual(
            settings.providers.hume_evi_voice_id,
            "22222222-2222-2222-2222-222222222222",
        )
        self.assertFalse(settings.providers.hume_evi_verbose_transcription)
        self.assertFalse(settings.providers.hume_evi_send_system_prompt)
        self.assertEqual(settings.prompt.hume_evi_system_prompt, "Hume Alicia prompt")
        self.assertEqual(settings.missing_agent_keys(), [])

    def test_daily_config_does_not_require_livekit_keys(self):
        settings = Settings.from_env(
            {
                "DAILY_API_KEY": "daily",
                "DEEPGRAM_API_KEY": "deepgram",
                "GOOGLE_API_KEY": "google",
                "CARTESIA_API_KEY": "cartesia",
                "VERBATIM_CARTESIA_VOICE_ID": "voice",
                "VERBATIM_TRANSPORT_PROVIDER": "daily",
            }
        )

        self.assertEqual(settings.missing_room_keys(), [])
        self.assertEqual(settings.missing_agent_keys(), [])

    def test_livekit_requires_livekit_keys_when_selected(self):
        settings = Settings.from_env(
            {
                "VERBATIM_TRANSPORT_PROVIDER": "livekit",
                "DEEPGRAM_API_KEY": "deepgram",
                "GOOGLE_API_KEY": "google",
                "CARTESIA_API_KEY": "cartesia",
                "VERBATIM_CARTESIA_VOICE_ID": "voice",
            }
        )

        self.assertEqual(
            settings.missing_room_keys(),
            ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"],
        )
        self.assertEqual(
            settings.missing_agent_keys(),
            ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"],
        )

    def test_livekit_does_not_require_daily_key_when_selected(self):
        settings = Settings.from_env(
            {
                "VERBATIM_TRANSPORT_PROVIDER": "livekit",
                "LIVEKIT_URL": "wss://example.livekit.cloud",
                "LIVEKIT_API_KEY": "livekit-key",
                "LIVEKIT_API_SECRET": "livekit-secret",
                "DEEPGRAM_API_KEY": "deepgram",
                "GOOGLE_API_KEY": "google",
                "CARTESIA_API_KEY": "cartesia",
                "VERBATIM_CARTESIA_VOICE_ID": "voice",
            }
        )

        self.assertEqual(settings.missing_room_keys(), [])
        self.assertEqual(settings.missing_agent_keys(), [])

    def test_openai_requires_only_openai_llm_key(self):
        settings = Settings.from_env(
            {
                "DAILY_API_KEY": "daily",
                "DEEPGRAM_API_KEY": "deepgram",
                "CARTESIA_API_KEY": "cartesia",
                "VERBATIM_CARTESIA_VOICE_ID": "voice",
                "VERBATIM_LLM_PROVIDER": "openai",
            }
        )

        self.assertEqual(settings.providers.llm_model, "gpt-4o-mini")
        self.assertEqual(settings.missing_agent_keys(), ["OPENAI_API_KEY"])

    def test_groq_requires_only_groq_llm_key(self):
        settings = Settings.from_env(
            {
                "DAILY_API_KEY": "daily",
                "DEEPGRAM_API_KEY": "deepgram",
                "CARTESIA_API_KEY": "cartesia",
                "VERBATIM_CARTESIA_VOICE_ID": "voice",
                "VERBATIM_LLM_PROVIDER": "groq",
            }
        )

        self.assertEqual(settings.providers.llm_model, "llama-3.1-8b-instant")
        self.assertEqual(settings.missing_agent_keys(), ["GROQ_API_KEY"])

    def test_qwen_requires_only_qwen_llm_key(self):
        settings = Settings.from_env(
            {
                "DAILY_API_KEY": "daily",
                "DEEPGRAM_API_KEY": "deepgram",
                "CARTESIA_API_KEY": "cartesia",
                "VERBATIM_CARTESIA_VOICE_ID": "voice",
                "VERBATIM_LLM_PROVIDER": "qwen",
            }
        )

        self.assertEqual(settings.providers.llm_model, "qwen3.5-2b")
        self.assertEqual(
            settings.providers.qwen_base_url,
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        )
        self.assertEqual(settings.missing_agent_keys(), ["QWEN_API_KEY"])

    def test_qwen_accepts_dashscope_api_key_alias(self):
        settings = Settings.from_env(
            {
                "DAILY_API_KEY": "daily",
                "DEEPGRAM_API_KEY": "deepgram",
                "CARTESIA_API_KEY": "cartesia",
                "VERBATIM_CARTESIA_VOICE_ID": "voice",
                "VERBATIM_LLM_PROVIDER": "qwen",
                "DASHSCOPE_API_KEY": "dashscope",
            }
        )

        self.assertEqual(settings.providers.qwen_api_key, "dashscope")
        self.assertEqual(settings.missing_agent_keys(), [])

    def test_xai_requires_only_xai_llm_key(self):
        settings = Settings.from_env(
            {
                "DAILY_API_KEY": "daily",
                "DEEPGRAM_API_KEY": "deepgram",
                "CARTESIA_API_KEY": "cartesia",
                "VERBATIM_CARTESIA_VOICE_ID": "voice",
                "VERBATIM_LLM_PROVIDER": "xai",
            }
        )

        self.assertEqual(settings.providers.llm_model, "grok-4-1-fast-non-reasoning")
        self.assertEqual(settings.providers.xai_base_url, "https://api.x.ai/v1")
        self.assertEqual(settings.missing_agent_keys(), ["XAI_API_KEY"])

    def test_mock_llm_requires_no_llm_key(self):
        settings = Settings.from_env(
            {
                "DAILY_API_KEY": "daily",
                "DEEPGRAM_API_KEY": "deepgram",
                "CARTESIA_API_KEY": "cartesia",
                "VERBATIM_CARTESIA_VOICE_ID": "voice",
                "VERBATIM_LLM_PROVIDER": "mock",
            }
        )

        self.assertEqual(settings.providers.llm_model, "mock-immediate")
        self.assertEqual(settings.missing_agent_keys(), [])

    def test_ultravox_requires_livekit_and_ultravox_key_only(self):
        settings = Settings.from_env(
            {
                "VERBATIM_TRANSPORT_PROVIDER": "livekit",
                "VERBATIM_LLM_PROVIDER": "ultravox",
            }
        )

        self.assertEqual(settings.providers.llm_model, "fixie-ai/ultravox")
        self.assertEqual(
            settings.missing_agent_keys(),
            ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "ULTRAVOX_API_KEY"],
        )

    def test_ultravox_does_not_require_deepgram_or_cartesia_keys(self):
        settings = Settings.from_env(
            {
                "VERBATIM_TRANSPORT_PROVIDER": "livekit",
                "LIVEKIT_URL": "wss://example.livekit.cloud",
                "LIVEKIT_API_KEY": "livekit-key",
                "LIVEKIT_API_SECRET": "livekit-secret",
                "VERBATIM_LLM_PROVIDER": "ultravox",
                "ULTRAVOX_API_KEY": "ultravox",
            }
        )

        self.assertEqual(settings.missing_agent_keys(), [])

    def test_deepgram_utterance_end_is_clamped_to_public_minimum(self):
        settings = Settings.from_env({"VERBATIM_DEEPGRAM_UTTERANCE_END_MS": "300"})

        self.assertEqual(settings.providers.deepgram_utterance_end_ms, 1000)


if __name__ == "__main__":
    unittest.main()
