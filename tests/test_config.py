from verbatim.config import Settings, clear_settings_cache, get_settings, validate_runtime_selection
import asyncio

from verbatim import hume
from verbatim.hume import create_hume_evi_session, hume_session_settings


def test_v2_defaults_are_livekit_groq_nova():
    settings = Settings.from_env({})
    assert settings.providers.transport_provider == "livekit"
    assert settings.providers.llm_provider == "groq"
    assert settings.providers.stt_provider == "deepgram"
    assert settings.providers.deepgram_model == "nova-3-general"


def test_existing_env_keys_are_loaded():
    settings = Settings.from_env(
        {
            "DAILY_API_KEY": "daily",
            "LIVEKIT_URL": "wss://example.livekit.cloud",
            "LIVEKIT_API_KEY": "lk-key",
            "LIVEKIT_API_SECRET": "lk-secret",
            "DEEPGRAM_API_KEY": "deepgram",
            "GOOGLE_API_KEY": "google",
            "OPENAI_API_KEY": "openai",
            "GROQ_API_KEY": "groq",
            "QWEN_API_KEY": "qwen",
            "XAI_API_KEY": "xai",
            "ULTRAVOX_API_KEY": "ultravox",
            "HUME_API_KEY": "hume",
            "HUME_SECRET_KEY": "hume-secret",
            "CARTESIA_API_KEY": "cartesia",
            "VERBATIM_CARTESIA_VOICE_ID": "voice",
            "NANGO_SECRET_KEY": "nango-secret",
            "NANGO_API_BASE_URL": "https://api.nango.dev",
            "NANGO_GOOGLE_CALENDAR_INTEGRATION_ID": "google-calendar",
            "TWILIO_ACCOUNT_SID": "twilio-sid",
            "TWILIO_AUTH_TOKEN": "twilio-token",
            "TWILIO_FROM_NUMBER": "+15550000000",
            "RESEND_API_KEY": "resend-key",
            "RESEND_FROM_EMAIL": "team@example.com",
            "VERBATIM_DEFAULT_FOLLOWUP_PHONE": "+15551112222",
            "VERBATIM_DEFAULT_FOLLOWUP_EMAIL": "caller@example.com",
            "VERBATIM_DEFAULT_CLIENT_ID": "client-a",
            "VERBATIM_TOOLS_ENABLED": "true",
            "VERBATIM_TOOL_TIMEOUT_MS": "2500",
        }
    )
    assert settings.providers.livekit_url == "wss://example.livekit.cloud"
    assert settings.providers.groq_api_key == "groq"
    assert settings.providers.hume_secret_key == "hume-secret"
    assert settings.voice.cartesia_voice_id == "voice"
    assert settings.integrations.nango_secret_key == "nango-secret"
    assert settings.integrations.twilio_account_sid == "twilio-sid"
    assert settings.integrations.resend_from_email == "team@example.com"
    assert settings.integrations.default_followup_phone == "+15551112222"
    assert settings.integrations.default_client_id == "client-a"
    assert settings.integrations.tools_enabled is True
    assert settings.integrations.tool_timeout_ms == 2500


def test_invalid_ultravox_daily_combo_is_rejected():
    settings = Settings.from_env(
        {
            "VERBATIM_TRANSPORT_PROVIDER": "daily",
            "VERBATIM_LLM_PROVIDER": "ultravox",
        }
    )
    try:
        validate_runtime_selection(settings)
    except ValueError as exc:
        assert "LiveKit" in str(exc)
    else:
        raise AssertionError("Expected invalid combo to fail")


def test_missing_agent_keys_are_scoped_to_selected_provider():
    settings = Settings.from_env(
        {
            "VERBATIM_TRANSPORT_PROVIDER": "livekit",
            "LIVEKIT_URL": "wss://example.livekit.cloud",
            "LIVEKIT_API_KEY": "lk-key",
            "LIVEKIT_API_SECRET": "lk-secret",
            "VERBATIM_LLM_PROVIDER": "mock",
            "DEEPGRAM_API_KEY": "deepgram",
            "CARTESIA_API_KEY": "cartesia",
            "VERBATIM_CARTESIA_VOICE_ID": "voice",
        }
    )
    assert settings.missing_agent_keys() == []


def test_default_prompts_do_not_include_old_identity_terms():
    settings = Settings.from_env({})
    hume_settings = hume_session_settings(settings, session_id="sess_test")
    active_prompt_text = " ".join(
        [
            settings.prompt.system_prompt,
            settings.prompt.greeting or "",
            hume_settings.get("system_prompt", ""),
            hume_settings.get("context", {}).get("text", ""),
        ]
    )
    blocked_terms = ["D" + "ubai", "C" + "RTG", "A" + "licia"]

    for term in blocked_terms:
        assert term not in active_prompt_text


def test_default_prompts_guide_viewing_and_sms_confirmation():
    settings = Settings.from_env({})
    hume_settings = hume_session_settings(settings, session_id="sess_test")
    active_prompt_text = " ".join(
        [
            settings.prompt.system_prompt,
            hume_settings.get("system_prompt", ""),
        ]
    ).lower()

    assert "property viewing" in active_prompt_text
    assert "sms confirmation" in active_prompt_text


def test_hume_config_is_opt_in_to_avoid_stale_remote_prompts():
    settings = Settings.from_env(
        {
            "HUME_EVI_CONFIG_ID": "remote-config",
            "HUME_EVI_CONFIG_VERSION": "7",
        }
    )

    assert settings.providers.hume_evi_config_id == "remote-config"
    assert settings.providers.hume_evi_config_version == 7
    assert settings.providers.hume_evi_use_config is False

    enabled = Settings.from_env(
        {
            "HUME_EVI_CONFIG_ID": "remote-config",
            "HUME_EVI_USE_CONFIG": "true",
        }
    )
    assert enabled.providers.hume_evi_use_config is True


def test_hume_session_omits_config_id_unless_enabled(monkeypatch):
    async def fake_token(settings):
        return {"access_token": "browser-token"}

    monkeypatch.setattr(hume, "_create_hume_access_token", fake_token)
    settings = Settings.from_env(
        {
            "HUME_API_KEY": "hume",
            "HUME_SECRET_KEY": "secret",
            "HUME_EVI_CONFIG_ID": "remote-config",
            "HUME_EVI_CONFIG_VERSION": "7",
        }
    )

    session = asyncio.run(create_hume_evi_session(settings, call_id="call_test", session_id="sess_test"))

    assert session["config_id"] is None
    assert session["config_version"] is None
    assert session["session_settings"]["system_prompt"] == settings.prompt.hume_evi_system_prompt


def test_hume_session_uses_config_when_explicitly_enabled(monkeypatch):
    async def fake_token(settings):
        return {"access_token": "browser-token"}

    monkeypatch.setattr(hume, "_create_hume_access_token", fake_token)
    settings = Settings.from_env(
        {
            "HUME_API_KEY": "hume",
            "HUME_SECRET_KEY": "secret",
            "HUME_EVI_CONFIG_ID": "remote-config",
            "HUME_EVI_CONFIG_VERSION": "7",
            "HUME_EVI_USE_CONFIG": "true",
        }
    )

    session = asyncio.run(create_hume_evi_session(settings, call_id="call_test", session_id="sess_test"))

    assert session["config_id"] == "remote-config"
    assert session["config_version"] == 7


def test_dotenv_overrides_inherited_environment_values(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        'VERBATIM_SYSTEM_PROMPT="Fresh prompt from file"\n'
        'VERBATIM_EVENT_LOG_PATH="./data/verbatim/fresh_events.jsonl"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("VERBATIM_SYSTEM_PROMPT", "stale inherited prompt")
    clear_settings_cache()

    settings = get_settings()

    assert settings.prompt.system_prompt == "Fresh prompt from file"
    assert settings.instrumentation.event_log_path.as_posix() == "data/verbatim/fresh_events.jsonl"
    clear_settings_cache()
