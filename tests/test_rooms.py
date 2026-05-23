import asyncio

from verbatim.config import Settings
from verbatim.rooms import DailyRoomManager, LiveKitRoomManager, derive_livekit_api_url


class Response:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class Client:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_daily_reuses_env_room():
    settings = Settings.from_env({"DAILY_ROOM_URL": "https://example.daily.co/room"})
    room = asyncio.run(DailyRoomManager(settings).resolve_room())
    assert room.room_url == "https://example.daily.co/room"
    assert room.source == "env"


def test_daily_create_room_uses_api():
    client = Client(Response(payload={"url": "https://example.daily.co/new"}))
    settings = Settings.from_env({"DAILY_API_KEY": "daily"})
    room = asyncio.run(DailyRoomManager(settings, http_client=client).resolve_room())
    assert room.room_url == "https://example.daily.co/new"
    assert client.calls[0][0] == "https://api.daily.co/v1/rooms"


def test_livekit_room_tokens_do_not_expose_secret():
    client = Client(Response())
    settings = Settings.from_env(
        {
            "LIVEKIT_URL": "wss://example.livekit.cloud",
            "LIVEKIT_API_KEY": "public-key",
            "LIVEKIT_API_SECRET": "super-secret",
        }
    )
    room = asyncio.run(LiveKitRoomManager(settings, http_client=client).resolve_room(call_id="call", session_id="sess"))
    assert room.room_url == "wss://example.livekit.cloud"
    assert "super-secret" not in room.room_token
    assert "super-secret" not in room.bot_token


def test_livekit_api_url_derives_from_ws_url():
    assert derive_livekit_api_url("wss://example.livekit.cloud") == "https://example.livekit.cloud"
