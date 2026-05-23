import asyncio
import base64
import json
import unittest

from verbatim.config import Settings
from verbatim.livekit import (
    LiveKitRoomManager,
    create_livekit_access_token,
    derive_livekit_api_url,
)


def _decode_payload(token: str) -> dict:
    payload = token.split(".")[1]
    padding = "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(f"{payload}{padding}"))


class FakeResponse:
    status_code = 200
    text = ""


class FakeClient:
    def __init__(self):
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse()


class LiveKitRoomManagerTests(unittest.TestCase):
    def test_derives_cloud_api_url(self):
        self.assertEqual(
            derive_livekit_api_url("wss://example.livekit.cloud"),
            "https://example.livekit.cloud",
        )

    def test_access_token_contains_grants_without_secret(self):
        token = create_livekit_access_token(
            api_key="key",
            api_secret="super-secret",
            room_name="room",
            identity="tester",
            name="Tester",
            ttl_seconds=60,
            can_publish_sources=["microphone"],
        )
        payload = _decode_payload(token)

        self.assertEqual(payload["iss"], "key")
        self.assertEqual(payload["sub"], "tester")
        self.assertEqual(payload["video"]["room"], "room")
        self.assertTrue(payload["video"]["roomJoin"])
        self.assertEqual(payload["video"]["canPublishSources"], ["microphone"])
        self.assertNotIn("super-secret", token)

    def test_resolve_room_creates_room_and_returns_browser_token_only(self):
        settings = Settings.from_env(
            {
                "VERBATIM_TRANSPORT_PROVIDER": "livekit",
                "LIVEKIT_URL": "wss://example.livekit.cloud",
                "LIVEKIT_API_KEY": "key",
                "LIVEKIT_API_SECRET": "super-secret",
            }
        )
        client = FakeClient()
        room = asyncio.run(
            LiveKitRoomManager(settings, http_client=client).resolve_room(
                call_id="call_123",
                session_id="sess_123",
            )
        )

        self.assertEqual(room.room_url, "wss://example.livekit.cloud")
        self.assertEqual(room.source, "created")
        self.assertEqual(client.calls[0][0], "https://example.livekit.cloud/twirp/livekit.RoomService/CreateRoom")
        self.assertNotEqual(room.room_token, room.bot_token)
        self.assertNotIn("super-secret", room.room_token)
        self.assertNotIn("super-secret", room.bot_token)
        self.assertEqual(_decode_payload(room.room_token)["sub"], "internal-call_123")
        self.assertEqual(_decode_payload(room.bot_token)["sub"], "agent_demo-call_123")
        self.assertNotIn("hidden", _decode_payload(room.bot_token)["video"])


if __name__ == "__main__":
    unittest.main()
