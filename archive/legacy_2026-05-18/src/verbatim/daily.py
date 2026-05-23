from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

from verbatim.config import Settings


@dataclass(frozen=True)
class DailyRoom:
    room_url: str
    room_token: str | None
    source: str
    geo: str | None = None


class DailyRoomError(RuntimeError):
    pass


class DailyRoomManager:
    def __init__(self, settings: Settings, http_client: Any | None = None) -> None:
        self.settings = settings
        self.http_client = http_client

    async def resolve_room(
        self,
        *,
        geo: str | None = None,
        force_create_room: bool | None = None,
    ) -> DailyRoom:
        providers = self.settings.providers
        selected_geo = geo if geo is not None else providers.daily_geo
        should_force_create = (
            providers.daily_force_create_room
            if force_create_room is None
            else force_create_room
        )
        if providers.daily_room_url and not should_force_create and not selected_geo:
            return DailyRoom(
                room_url=providers.daily_room_url,
                room_token=providers.daily_room_token,
                source="env",
                geo=None,
            )
        if not providers.daily_api_key:
            raise DailyRoomError("DAILY_API_KEY is required when DAILY_ROOM_URL is not set.")
        return await self._create_room(geo=selected_geo)

    async def _create_room(self, *, geo: str | None = None) -> DailyRoom:
        payload = {
            "privacy": "public",
            "properties": {
                "exp": int(time.time()) + self.settings.session.room_ttl_seconds,
                "eject_at_room_exp": True,
                "enable_prejoin_ui": True,
            },
        }
        if geo:
            payload["properties"]["geo"] = geo
        headers = {"Authorization": f"Bearer {self.settings.providers.daily_api_key}"}

        if self.http_client is not None:
            response = await self.http_client.post(
                "https://api.daily.co/v1/rooms",
                headers=headers,
                json=payload,
                timeout=10,
            )
            return self._room_from_response(response, geo=geo)

        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.daily.co/v1/rooms",
                headers=headers,
                json=payload,
                timeout=10,
            )
        return self._room_from_response(response, geo=geo)

    def _room_from_response(self, response: Any, *, geo: str | None = None) -> DailyRoom:
        status_code = getattr(response, "status_code", 200)
        if status_code >= 400:
            text = getattr(response, "text", "")
            raise DailyRoomError(f"Daily room creation failed with HTTP {status_code}: {text}")
        data = response.json()
        room_url = data.get("url")
        if not room_url:
            raise DailyRoomError("Daily room creation response did not include a room URL.")
        return DailyRoom(room_url=room_url, room_token=None, source="created", geo=geo)
