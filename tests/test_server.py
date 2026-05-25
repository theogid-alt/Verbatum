from fastapi.testclient import TestClient

from verbatim.config import clear_settings_cache
import verbatim.server as server
from verbatim.server import create_app


def test_config_response_does_not_expose_secrets(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LIVEKIT_API_SECRET", "secret-value")
    monkeypatch.setenv("LIVEKIT_API_KEY", "key-value")
    monkeypatch.setenv("HUME_SECRET_KEY", "hume-secret")
    monkeypatch.setenv("NANGO_SECRET_KEY", "nango-secret")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "twilio-secret")
    monkeypatch.setenv("RESEND_API_KEY", "resend-secret")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "team@example.com")
    clear_settings_cache()
    response = TestClient(create_app()).get("/api/config")
    assert response.status_code == 200
    payload = response.json()
    assert "secret-value" not in str(payload)
    assert "hume-secret" not in str(payload)
    assert "nango-secret" not in str(payload)
    assert "twilio-secret" not in str(payload)
    assert "resend-secret" not in str(payload)
    assert payload["integration_catalog"]["providers"][0]["configured"] is True


def test_direct_tools_are_browser_visible_without_secret_leak(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "twilio-secret")
    monkeypatch.setenv("TWILIO_FROM_NUMBER", "+15550000000")
    monkeypatch.setenv("RESEND_API_KEY", "resend-secret")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "team@example.com")
    clear_settings_cache()

    response = TestClient(create_app()).get("/api/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["direct_tools_configured"] is True
    assert "twilio-secret" not in str(payload)
    assert "resend-secret" not in str(payload)
    direct_provider = [provider for provider in payload["integration_catalog"]["providers"] if provider["id"] == "direct"][0]
    assert direct_provider["configured"] is True
    assert direct_provider["integrations"][0]["allowed_tools"] == ["send_sms_followup"]
    assert "send_email_followup" not in str(direct_provider)


def test_start_agent_missing_keys_returns_400(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    clear_settings_cache()
    response = TestClient(create_app()).post(
        "/api/agent/start",
        json={
            "transport_provider": "livekit",
            "room_url": "wss://example.livekit.cloud",
            "room_name": "room",
            "llm_provider": "mock",
            "tools_enabled": False,
        },
    )
    assert response.status_code == 400
    assert "Missing required agent environment variables" in response.json()["detail"]


def test_start_agent_accepts_call_context_without_response_leak(monkeypatch, tmp_path):
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

    response = TestClient(create_app()).post(
        "/api/agent/start",
        json={
            "transport_provider": "livekit",
            "room_url": "wss://example.livekit.cloud",
            "room_name": "room",
            "llm_provider": "mock",
            "tools_enabled": False,
            "knowledge_base": "Hidden listing detail: top-floor penthouse.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert captured["knowledge_base"] == "Hidden listing detail: top-floor penthouse."
    assert "call_notes" not in captured
    assert payload["knowledge_base_configured"] is True
    assert "top-floor penthouse" not in str(payload)


def test_hume_session_missing_keys_returns_400(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    clear_settings_cache()
    response = TestClient(create_app()).post("/api/hume/evi/session", json={})
    assert response.status_code == 400
    assert "HUME_API_KEY" in response.json()["detail"]


def test_nango_connect_session_requires_secret(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NANGO_SECRET_KEY", raising=False)
    clear_settings_cache()
    response = TestClient(create_app()).post(
        "/api/integrations/nango/connect-session",
        json={"client_id": "client-a", "integration_key": "google-calendar"},
    )

    assert response.status_code == 400
    assert "NANGO_SECRET_KEY" in response.json()["detail"]


def test_integration_status_is_browser_safe(monkeypatch, tmp_path):
    class FakeNangoClient:
        def __init__(self, settings):
            pass

        async def list_connections(self, *, client_id, integration_key):
            return []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NANGO_SECRET_KEY", "nango-secret")
    monkeypatch.setenv("VERBATIM_INTEGRATIONS_DB_PATH", str(tmp_path / "integrations.db"))
    monkeypatch.setattr(server, "NangoClient", FakeNangoClient)
    clear_settings_cache()

    response = TestClient(create_app()).get("/api/integrations/status?client_id=client-a")

    assert response.status_code == 200
    payload = response.json()
    assert payload["client_id"] == "client-a"
    assert "nango-secret" not in str(payload)
    google_calendar = next(card for card in payload["cards"] if card["id"] == "google_calendar")
    assert google_calendar["allowed_tools"]
    assert google_calendar["status"] == "not_connected"


def test_start_agent_rejects_ultravox_tool_combo(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    clear_settings_cache()
    response = TestClient(create_app()).post(
        "/api/agent/start",
        json={
            "transport_provider": "livekit",
            "room_url": "wss://example.livekit.cloud",
            "room_name": "room",
            "llm_provider": "ultravox",
            "tools_enabled": True,
        },
    )

    assert response.status_code == 400
    assert "Tool calling" in response.json()["detail"]
