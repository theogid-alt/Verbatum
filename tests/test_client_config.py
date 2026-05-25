import os

from fastapi.testclient import TestClient

from verbatim.client_config import ClientConfigStore
from verbatim.config import Settings, clear_settings_cache
import verbatim.server as server
from verbatim.server import create_app


def test_client_config_defaults_create_local_files(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    clear_settings_cache()
    settings = Settings.from_env({})

    config = ClientConfigStore().read(settings)

    assert (tmp_path / "client" / "profile.json").exists()
    assert (tmp_path / "client" / "prompt.md").exists()
    assert (tmp_path / "client" / "kb.md").exists()
    assert (tmp_path / "client" / "integrations.json").exists()
    assert config.profile["profile_id"] == "demo"
    assert "google_calendar" in config.integrations["integrations"]
    assert "salesforce" in config.integrations["integrations"]
    assert "make" in config.integrations["integrations"]
    assert "whatsapp_business" in config.integrations["integrations"]


def test_client_config_save_preserves_hidden_profile_id(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    clear_settings_cache()
    settings = Settings.from_env({"VERBATIM_DEFAULT_CLIENT_ID": "client-alpha"})
    store = ClientConfigStore()

    first = store.read(settings)
    updated = store.update_profile(settings, {"business_name": "Acme Homes", "profile_id": "ignored"})

    assert first.profile["profile_id"] == "client-alpha"
    assert updated["profile_id"] == "client-alpha"
    assert updated["business_name"] == "Acme Homes"


def test_client_config_endpoint_is_browser_safe(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NANGO_SECRET_KEY", "nango-secret")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "twilio-secret")
    monkeypatch.setenv("TWILIO_FROM_NUMBER", "+15550000000")
    clear_settings_cache()

    response = TestClient(create_app()).get("/api/client-config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["profile_id"] == "demo"
    assert payload["integration_catalog"]["cards"]
    assert "nango-secret" not in str(payload)
    assert "twilio-secret" not in str(payload)


def test_start_agent_uses_saved_prompt_kb_and_profile_id(monkeypatch, tmp_path):
    class FakeProcess:
        pid = 1234
        returncode = 0

        def terminate(self):
            self.returncode = 0

        async def wait(self):
            return self.returncode

    captured = {}

    async def fake_spawn(payload):
        captured.update(payload)
        return FakeProcess()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LIVEKIT_URL", "wss://example.livekit.cloud")
    monkeypatch.setenv("LIVEKIT_API_KEY", "livekit-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "livekit-secret")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "deepgram-key")
    monkeypatch.setenv("CARTESIA_API_KEY", "cartesia-key")
    monkeypatch.setenv("VERBATIM_CARTESIA_VOICE_ID", "voice-id")
    monkeypatch.setattr(server, "_spawn_agent_worker", fake_spawn)
    server.ACTIVE_AGENT.clear()
    clear_settings_cache()
    client = TestClient(create_app())
    client.put("/api/client-config/prompt", json={"content": "Saved prompt."})
    client.put("/api/client-config/kb", json={"content": "Saved KB."})

    response = client.post(
        "/api/agent/start",
        json={
            "transport_provider": "livekit",
            "room_url": "wss://example.livekit.cloud",
            "room_name": "room",
            "llm_provider": "mock",
            "tools_enabled": False,
        },
    )

    assert response.status_code == 200
    assert captured["client_id"] == "demo"
    assert captured["system_prompt"].startswith("Saved prompt.")
    assert "Assistant name: Alicia." in captured["system_prompt"]
    assert "Business name: Demo Business." in captured["system_prompt"]
    assert captured["knowledge_base"] == "Saved KB."


def test_reset_client_profile_prompt_kb_preserves_integrations(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VERBATIM_DEFAULT_CLIENT_ID", "client-alpha")
    monkeypatch.setenv("VERBATIM_SYSTEM_PROMPT", "Baseline prompt.")
    monkeypatch.setenv("VERBATIM_TRANSPORT_PROVIDER", "livekit")
    monkeypatch.setenv("VERBATIM_STT_PROVIDER", "deepgram_flux")
    monkeypatch.setenv("VERBATIM_DEEPGRAM_MODEL", "flux-general-en")
    monkeypatch.setenv("VERBATIM_LLM_PROVIDER", "groq")
    monkeypatch.setenv("VERBATIM_GROQ_MODEL", "llama-3.1-8b-instant")
    clear_settings_cache()
    client = TestClient(create_app())
    client.put(
        "/api/client-config/profile",
        json={
            "business_name": "Changed Business",
            "transport_provider": "daily",
            "stt_provider": "deepgram",
            "deepgram_model": "nova-3-general",
            "llm_provider": "mock",
            "llm_model": "mock-immediate",
        },
    )
    client.put("/api/client-config/prompt", json={"content": "Changed prompt."})
    client.put("/api/client-config/kb", json={"content": "Changed KB."})
    client.put("/api/client-config/integrations", json={"integrations": {"google_calendar": {"enabled": False}}})

    response = client.post("/api/client-config/reset", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["profile_id"] == "client-alpha"
    assert payload["profile"]["business_name"] == "Demo Business"
    assert payload["profile"]["transport_provider"] == "livekit"
    assert payload["profile"]["stt_provider"] == "deepgram_flux"
    assert payload["profile"]["deepgram_model"] == "flux-general-en"
    assert payload["profile"]["llm_provider"] == "groq"
    assert payload["profile"]["llm_model"] == "llama-3.1-8b-instant"
    assert payload["prompt"]["content"].strip() == "Baseline prompt."
    assert payload["knowledge_base"]["content"] == ""
    assert payload["integrations"]["integrations"]["google_calendar"]["enabled"] is False


def test_disabled_integrations_are_not_exposed_as_enabled_tools(monkeypatch, tmp_path):
    class FakeProcess:
        pid = 1234
        returncode = 0

        def terminate(self):
            self.returncode = 0

        async def wait(self):
            return self.returncode

    captured = {}

    async def fake_spawn(payload):
        captured.update(payload)
        return FakeProcess()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LIVEKIT_URL", "wss://example.livekit.cloud")
    monkeypatch.setenv("LIVEKIT_API_KEY", "livekit-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "livekit-secret")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "deepgram-key")
    monkeypatch.setenv("CARTESIA_API_KEY", "cartesia-key")
    monkeypatch.setenv("VERBATIM_CARTESIA_VOICE_ID", "voice-id")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "twilio-secret")
    monkeypatch.setenv("TWILIO_FROM_NUMBER", "+15550000000")
    monkeypatch.setattr(server, "_spawn_agent_worker", fake_spawn)
    server.ACTIVE_AGENT.clear()
    clear_settings_cache()
    client = TestClient(create_app())
    client.put("/api/client-config/integrations", json={"integrations": {"google_calendar": {"enabled": False}}})

    response = client.post(
        "/api/agent/start",
        json={
            "transport_provider": "livekit",
            "room_url": "wss://example.livekit.cloud",
            "room_name": "room",
            "llm_provider": "mock",
            "tools_enabled": True,
        },
    )

    assert response.status_code == 200
    assert captured["enabled_tools"] == ["send_sms_followup"]


def test_disconnect_disables_calendar_and_removes_local_connection(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NANGO_SECRET_KEY", "nango-secret")
    monkeypatch.setenv("VERBATIM_INTEGRATIONS_DB_PATH", str(tmp_path / "integrations.db"))
    clear_settings_cache()
    settings = Settings.from_env(dict(os.environ))
    store = server._integration_store(settings)
    store.upsert_connection(
        client_id="demo",
        provider="nango",
        integration_key="google-calendar",
        connection_id="conn_123",
        status="connected",
    )

    response = TestClient(create_app()).post("/api/integrations/google_calendar/disconnect", json={})

    assert response.status_code == 200
    payload = response.json()
    card = next(item for item in payload["integration_catalog"]["cards"] if item["id"] == "google_calendar")
    assert card["enabled"] is False
    assert store.get_connection(client_id="demo", provider="nango", integration_key="google-calendar") is None


def test_nango_connect_session_works_for_non_calendar_cards(monkeypatch, tmp_path):
    class FakeNangoClient:
        def __init__(self, settings):
            pass

        async def create_connect_session(self, *, client_id, integration_key):
            captured["client_id"] = client_id
            captured["integration_key"] = integration_key
            return {"connect_link": "https://connect.example/session", "expires_at": "soon"}

    captured = {}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NANGO_SECRET_KEY", "nango-secret")
    monkeypatch.setenv("NANGO_SALESFORCE_INTEGRATION_ID", "verbatim-salesforce")
    monkeypatch.setenv("VERBATIM_INTEGRATIONS_DB_PATH", str(tmp_path / "integrations.db"))
    monkeypatch.setattr(server, "NangoClient", FakeNangoClient)
    clear_settings_cache()

    response = TestClient(create_app()).post(
        "/api/integrations/nango/connect-session",
        json={"integration_id": "salesforce"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["integration_id"] == "salesforce"
    assert payload["integration_key"] == "verbatim-salesforce"
    assert captured == {"client_id": "demo", "integration_key": "verbatim-salesforce"}


def test_nango_card_status_uses_matching_connection(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NANGO_SECRET_KEY", "nango-secret")
    monkeypatch.setenv("NANGO_SLACK_INTEGRATION_ID", "slack-prod")
    monkeypatch.setenv("VERBATIM_INTEGRATIONS_DB_PATH", str(tmp_path / "integrations.db"))
    clear_settings_cache()
    client = TestClient(create_app())
    client.put("/api/client-config/integrations", json={"integrations": {"slack": {"enabled": True}}})
    settings = Settings.from_env(dict(os.environ))
    server._integration_store(settings).upsert_connection(
        client_id="demo",
        provider="nango",
        integration_key="slack-prod",
        connection_id="slack_conn",
        status="connected",
    )

    response = client.get("/api/client-config")

    assert response.status_code == 200
    card = next(item for item in response.json()["integration_catalog"]["cards"] if item["id"] == "slack")
    assert card["enabled"] is True
    assert card["ready"] is True
    assert card["status"] == "connected"


def test_nango_card_with_error_status_is_still_ready_when_connection_id_exists(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NANGO_SECRET_KEY", "nango-secret")
    monkeypatch.setenv("VERBATIM_INTEGRATIONS_DB_PATH", str(tmp_path / "integrations.db"))
    clear_settings_cache()
    settings = Settings.from_env(dict(os.environ))
    server._integration_store(settings).upsert_connection(
        client_id="demo",
        provider="nango",
        integration_key=settings.integrations.nango_google_calendar_integration_id,
        connection_id="calendar_conn",
        status="error",
    )

    response = TestClient(create_app()).get("/api/client-config")

    assert response.status_code == 200
    card = next(item for item in response.json()["integration_catalog"]["cards"] if item["id"] == "google_calendar")
    assert card["ready"] is True
    assert card["status"] == "connected"


def test_webhook_and_manual_api_cards_report_env_status(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MAKE_WEBHOOK_URL", "https://hooks.example/make")
    monkeypatch.setenv("ZENCHEF_API_KEY", "zen-secret")
    clear_settings_cache()
    client = TestClient(create_app())
    client.put(
        "/api/client-config/integrations",
        json={"integrations": {"make": {"enabled": True}, "zenchef": {"enabled": True}}},
    )

    response = client.get("/api/client-config")

    assert response.status_code == 200
    cards = response.json()["integration_catalog"]["cards"]
    make_card = next(item for item in cards if item["id"] == "make")
    zenchef_card = next(item for item in cards if item["id"] == "zenchef")
    assert make_card["ready"] is True
    assert zenchef_card["ready"] is True
    assert "zen-secret" not in str(response.json())
