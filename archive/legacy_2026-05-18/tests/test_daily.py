import asyncio
import unittest

from verbatim.config import Settings
from verbatim.daily import DailyRoomManager


class FakeResponse:
    status_code = 200
    text = ""

    def json(self):
        return {"url": "https://example.daily.co/test-room"}


class FakeClient:
    def __init__(self):
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse()


class DailyRoomManagerTests(unittest.TestCase):
    def test_reuses_env_room(self):
        settings = Settings.from_env({"DAILY_ROOM_URL": "https://example.daily.co/env"})
        room = asyncio.run(DailyRoomManager(settings).resolve_room())
        self.assertEqual(room.room_url, "https://example.daily.co/env")
        self.assertEqual(room.source, "env")

    def test_creates_room_with_daily_api(self):
        settings = Settings.from_env({"DAILY_API_KEY": "daily"})
        client = FakeClient()
        room = asyncio.run(DailyRoomManager(settings, http_client=client).resolve_room())
        self.assertEqual(room.room_url, "https://example.daily.co/test-room")
        self.assertEqual(room.source, "created")
        self.assertEqual(client.calls[0][1]["headers"]["Authorization"], "Bearer daily")

    def test_creates_room_with_daily_geo(self):
        settings = Settings.from_env({"DAILY_API_KEY": "daily", "DAILY_GEO": "eu-central-1"})
        client = FakeClient()
        room = asyncio.run(DailyRoomManager(settings, http_client=client).resolve_room())
        self.assertEqual(room.geo, "eu-central-1")
        self.assertEqual(
            client.calls[0][1]["json"]["properties"]["geo"],
            "eu-central-1",
        )

    def test_geo_forces_created_room_when_env_room_exists(self):
        settings = Settings.from_env(
            {
                "DAILY_API_KEY": "daily",
                "DAILY_ROOM_URL": "https://example.daily.co/env",
                "DAILY_GEO": "eu-west-2",
            }
        )
        client = FakeClient()
        room = asyncio.run(DailyRoomManager(settings, http_client=client).resolve_room())
        self.assertEqual(room.source, "created")
        self.assertEqual(room.geo, "eu-west-2")
        self.assertEqual(client.calls[0][1]["json"]["properties"]["geo"], "eu-west-2")


if __name__ == "__main__":
    unittest.main()
