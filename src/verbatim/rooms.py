from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from verbatim.config import Settings


@dataclass(frozen=True)
class Room:
    transport_provider: str
    room_url: str
    room_name: str | None
    room_token: str | None
    bot_token: str | None
    source: str
    room_geo: str | None = None


class RoomError(RuntimeError):
    pass


async def resolve_room(settings: Settings, *, call_id: str, session_id: str) -> Room:
    provider = settings.providers.transport_provider
    if provider == "daily":
        return await DailyRoomManager(settings).resolve_room()
    if provider == "livekit":
        return await LiveKitRoomManager(settings).resolve_room(call_id=call_id, session_id=session_id)
    raise RoomError(f"{provider} does not use /api/rooms.")


class DailyRoomManager:
    def __init__(self, settings: Settings, http_client: Any | None = None) -> None:
        self.settings = settings
        self.http_client = http_client

    async def resolve_room(self) -> Room:
        providers = self.settings.providers
        if providers.daily_room_url and not providers.daily_force_create_room and not providers.daily_geo:
            return Room(
                transport_provider="daily",
                room_url=providers.daily_room_url,
                room_name=None,
                room_token=providers.daily_room_token,
                bot_token=providers.daily_room_token,
                source="env",
            )
        if not providers.daily_api_key:
            raise RoomError("DAILY_API_KEY is required when DAILY_ROOM_URL is not set.")
        return await self._create_room()

    async def _create_room(self) -> Room:
        import httpx

        providers = self.settings.providers
        payload: dict[str, Any] = {
            "privacy": "public",
            "properties": {
                "exp": int(time.time()) + self.settings.session.room_ttl_seconds,
                "eject_at_room_exp": True,
                "enable_prejoin_ui": True,
            },
        }
        if providers.daily_geo:
            payload["properties"]["geo"] = providers.daily_geo
        headers = {"Authorization": f"Bearer {providers.daily_api_key}"}
        client = self.http_client or httpx.AsyncClient()
        close_client = self.http_client is None
        try:
            response = await client.post(
                "https://api.daily.co/v1/rooms",
                headers=headers,
                json=payload,
                timeout=10,
            )
        finally:
            if close_client:
                await client.aclose()
        if response.status_code >= 400:
            raise RoomError(f"Daily room creation failed with HTTP {response.status_code}.")
        data = response.json()
        room_url = data.get("url")
        if not room_url:
            raise RoomError("Daily room creation response did not include a room URL.")
        return Room(
            transport_provider="daily",
            room_url=room_url,
            room_name=None,
            room_token=None,
            bot_token=None,
            source="created",
            room_geo=providers.daily_geo,
        )


class LiveKitRoomManager:
    def __init__(self, settings: Settings, http_client: Any | None = None) -> None:
        self.settings = settings
        self.http_client = http_client

    async def resolve_room(self, *, call_id: str, session_id: str) -> Room:
        providers = self.settings.providers
        if not providers.livekit_url or not providers.livekit_api_key or not providers.livekit_api_secret:
            raise RoomError("LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET are required.")
        room_name = providers.livekit_room_name or f"verbatim-{secrets.token_hex(6)}"
        source = "env" if providers.livekit_room_name else "created"
        if not providers.livekit_room_name:
            await self._create_room(room_name)
        return Room(
            transport_provider="livekit",
            room_url=providers.livekit_url,
            room_name=room_name,
            room_token=self._token(room_name, identity=f"{self.settings.agent.client_id}-{call_id}", name="Verbatim tester", publish_sources=["microphone"]),
            bot_token=self._token(room_name, identity=f"{self.settings.agent.agent_id}-{call_id}", name=self.settings.session.bot_name),
            source=source,
        )

    def bot_token(self, *, room_name: str, call_id: str) -> str:
        return self._token(room_name, identity=f"{self.settings.agent.agent_id}-{call_id}", name=self.settings.session.bot_name)

    async def _create_room(self, room_name: str) -> None:
        import httpx

        providers = self.settings.providers
        api_url = derive_livekit_api_url(providers.livekit_url or "", providers.livekit_api_url)
        token = create_livekit_access_token(
            api_key=providers.livekit_api_key or "",
            api_secret=providers.livekit_api_secret or "",
            room_name=room_name,
            identity=f"{self.settings.agent.agent_id}-room-admin",
            name="Verbatim room admin",
            ttl_seconds=60,
            room_create=True,
        )
        payload = {
            "name": room_name,
            "emptyTimeout": providers.livekit_empty_timeout_seconds,
            "maxParticipants": providers.livekit_max_participants,
        }
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        client = self.http_client or httpx.AsyncClient()
        close_client = self.http_client is None
        try:
            response = await client.post(
                f"{api_url}/twirp/livekit.RoomService/CreateRoom",
                headers=headers,
                json=payload,
                timeout=10,
            )
        finally:
            if close_client:
                await client.aclose()
        if response.status_code < 400:
            return
        if response.status_code == 409 or "already" in getattr(response, "text", "").lower():
            return
        raise RoomError(f"LiveKit room creation failed with HTTP {response.status_code}.")

    def _token(
        self,
        room_name: str,
        *,
        identity: str,
        name: str,
        publish_sources: list[str] | None = None,
    ) -> str:
        providers = self.settings.providers
        return create_livekit_access_token(
            api_key=providers.livekit_api_key or "",
            api_secret=providers.livekit_api_secret or "",
            room_name=room_name,
            identity=identity,
            name=name,
            ttl_seconds=providers.livekit_token_ttl_seconds,
            can_publish=True,
            can_subscribe=True,
            can_publish_sources=publish_sources,
        )


def derive_livekit_api_url(livekit_url: str, explicit_api_url: str | None = None) -> str:
    if explicit_api_url:
        return explicit_api_url.rstrip("/")
    if livekit_url.startswith("wss://"):
        return f"https://{livekit_url.removeprefix('wss://')}".rstrip("/")
    if livekit_url.startswith("ws://"):
        return f"http://{livekit_url.removeprefix('ws://')}".rstrip("/")
    return livekit_url.rstrip("/")


def create_livekit_access_token(
    *,
    api_key: str,
    api_secret: str,
    room_name: str,
    identity: str,
    name: str,
    ttl_seconds: int,
    can_publish: bool = True,
    can_subscribe: bool = True,
    room_create: bool | None = None,
    can_publish_sources: list[str] | None = None,
) -> str:
    now = int(time.time())
    video: dict[str, Any] = {
        "roomJoin": True,
        "room": room_name,
        "canPublish": can_publish,
        "canSubscribe": can_subscribe,
        "canPublishData": True,
    }
    if room_create is not None:
        video["roomCreate"] = room_create
    if can_publish_sources:
        video["canPublishSources"] = can_publish_sources
    claims = {
        "iss": api_key,
        "sub": identity,
        "name": name,
        "nbf": now,
        "exp": now + ttl_seconds,
        "video": video,
    }
    return _jwt_encode(claims, api_secret)


def _jwt_encode(payload: dict[str, Any], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = f"{_base64url_json(header)}.{_base64url_json(payload)}"
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
    return f"{signing_input}.{_base64url(signature)}"


def _base64url_json(value: dict[str, Any]) -> str:
    return _base64url(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
