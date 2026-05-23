import unittest

from verbatim.config import Settings
from verbatim.stt_config import (
    settings_with_llm_override,
    settings_with_stt_override,
    settings_with_transport_override,
)


class ServerConfigTests(unittest.TestCase):
    def test_nova_option_switches_to_standard_deepgram(self):
        settings = Settings.from_env({})
        overridden = settings_with_stt_override(
            settings,
            stt_provider="deepgram",
            deepgram_model="nova-3-general",
        )

        self.assertEqual(overridden.providers.stt_provider, "deepgram")
        self.assertEqual(overridden.providers.deepgram_model, "nova-3-general")

    def test_flux_option_uses_flux_model(self):
        settings = Settings.from_env({})
        overridden = settings_with_stt_override(
            settings,
            stt_provider="deepgram_flux",
            deepgram_model="nova-3-general",
        )

        self.assertEqual(overridden.providers.stt_provider, "deepgram_flux")
        self.assertEqual(overridden.providers.deepgram_model, "flux-general-en")

    def test_unknown_stt_provider_is_rejected(self):
        settings = Settings.from_env({})

        with self.assertRaises(ValueError):
            settings_with_stt_override(
                settings,
                stt_provider="not-real",
                deepgram_model="nova-3-general",
            )

    def test_openai_option_switches_model(self):
        settings = Settings.from_env({})
        overridden = settings_with_llm_override(
            settings,
            llm_provider="openai",
            llm_model="gpt-4o-mini",
        )

        self.assertEqual(overridden.providers.llm_provider, "openai")
        self.assertEqual(overridden.providers.llm_model, "gpt-4o-mini")

    def test_groq_option_switches_model(self):
        settings = Settings.from_env({})
        overridden = settings_with_llm_override(
            settings,
            llm_provider="groq",
            llm_model="llama-3.1-8b-instant",
        )

        self.assertEqual(overridden.providers.llm_provider, "groq")
        self.assertEqual(overridden.providers.llm_model, "llama-3.1-8b-instant")

    def test_qwen_option_switches_model(self):
        settings = Settings.from_env({})
        overridden = settings_with_llm_override(
            settings,
            llm_provider="qwen",
            llm_model="qwen3.5-2b",
        )

        self.assertEqual(overridden.providers.llm_provider, "qwen")
        self.assertEqual(overridden.providers.llm_model, "qwen3.5-2b")

    def test_qwen_model_alias_switches_provider(self):
        settings = Settings.from_env({})
        overridden = settings_with_llm_override(
            settings,
            llm_provider="qwen3.5-2b",
            llm_model=None,
        )

        self.assertEqual(overridden.providers.llm_provider, "qwen")
        self.assertEqual(overridden.providers.llm_model, "qwen3.5-2b")

    def test_xai_option_switches_model(self):
        settings = Settings.from_env({})
        overridden = settings_with_llm_override(
            settings,
            llm_provider="xai",
            llm_model="grok-4-1-fast-non-reasoning",
        )

        self.assertEqual(overridden.providers.llm_provider, "xai")
        self.assertEqual(overridden.providers.llm_model, "grok-4-1-fast-non-reasoning")

    def test_xai_model_alias_switches_provider(self):
        settings = Settings.from_env({})
        overridden = settings_with_llm_override(
            settings,
            llm_provider="grok-4-1-fast-non-reasoning",
            llm_model=None,
        )

        self.assertEqual(overridden.providers.llm_provider, "xai")
        self.assertEqual(overridden.providers.llm_model, "grok-4-1-fast-non-reasoning")

    def test_ultravox_option_switches_model(self):
        settings = Settings.from_env({})
        overridden = settings_with_llm_override(
            settings,
            llm_provider="ultravox",
            llm_model="fixie-ai/ultravox",
        )

        self.assertEqual(overridden.providers.llm_provider, "ultravox")
        self.assertEqual(overridden.providers.llm_model, "fixie-ai/ultravox")

    def test_ultravox_model_alias_switches_provider(self):
        settings = Settings.from_env({})
        overridden = settings_with_llm_override(
            settings,
            llm_provider="fixie-ai/ultravox",
            llm_model=None,
        )

        self.assertEqual(overridden.providers.llm_provider, "ultravox")
        self.assertEqual(overridden.providers.llm_model, "fixie-ai/ultravox")

    def test_unknown_llm_provider_is_rejected(self):
        settings = Settings.from_env({})

        with self.assertRaises(ValueError):
            settings_with_llm_override(
                settings,
                llm_provider="not-real",
                llm_model="anything",
            )

    def test_livekit_transport_override(self):
        settings = Settings.from_env({})
        overridden = settings_with_transport_override(settings, transport_provider="livekit")

        self.assertEqual(overridden.providers.transport_provider, "livekit")

    def test_unknown_transport_provider_is_rejected(self):
        settings = Settings.from_env({})

        with self.assertRaises(ValueError):
            settings_with_transport_override(settings, transport_provider="not-real")


if __name__ == "__main__":
    unittest.main()
