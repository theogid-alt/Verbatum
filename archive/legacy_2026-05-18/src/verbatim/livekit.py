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
class LiveKitRoom:
    room_url: str
    room_name: str
    room_token: str
    bot_token: str
    source: str


class LiveKitRoomError(RuntimeError):
    pass


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
    hidden: bool | None = None,
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
    if hidden is not None:
        video["hidden"] = hidden
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
    encoded_header = _base64url_json(header)
    encoded_payload = _base64url_json(payload)
    signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_payload}.{_base64url(signature)}"


def _base64url_json(value: dict[str, Any]) -> str:
    return _base64url(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


class LiveKitRoomManager:
    def __init__(self, settings: Settings, http_client: Any | None = None) -> None:
        self.settings = settings
        self.http_client = http_client

    async def resolve_room(self, *, call_id: str, session_id: str) -> LiveKitRoom:
        providers = self.settings.providers
        missing = self.settings.missing_room_keys("livekit")
        if missing:
            raise LiveKitRoomError(
                f"Missing required LiveKit environment variables: {', '.join(missing)}"
            )
        assert providers.livekit_url
        assert providers.livekit_api_key
        assert providers.livekit_api_secret

        room_name = providers.livekit_room_name or f"verbatim-{secrets.token_hex(6)}"
        source = "env" if providers.livekit_room_name else "created"
        if not providers.livekit_room_name:
            await self._create_room(room_name)

        browser_token = self.browser_token(room_name=room_name, call_id=call_id)
        bot_token = self.bot_token(room_name=room_name, call_id=call_id)
        return LiveKitRoom(
            room_url=providers.livekit_url,
            room_name=room_name,
            room_token=browser_token,
            bot_token=bot_token,
            source=source,
        )

    def browser_token(self, *, room_name: str, call_id: str) -> str:
        providers = self.settings.providers
        assert providers.livekit_api_key
        assert providers.livekit_api_secret
        return create_livekit_access_token(
            api_key=providers.livekit_api_key,
            api_secret=providers.livekit_api_secret,
            room_name=room_name,
            identity=f"{self.settings.agent.client_id}-{call_id}",
            name="Verbatim tester",
            ttl_seconds=providers.livekit_token_ttl_seconds,
            can_publish=True,
            can_subscribe=True,
            can_publish_sources=["microphone"],
        )

    def bot_token(self, *, room_name: str, call_id: str) -> str:
        providers = self.settings.providers
        assert providers.livekit_api_key
        assert providers.livekit_api_secret
        return create_livekit_access_token(
            api_key=providers.livekit_api_key,
            api_secret=providers.livekit_api_secret,
            room_name=room_name,
            identity=f"{self.settings.agent.agent_id}-{call_id}",
            name=self.settings.session.bot_name,
            ttl_seconds=providers.livekit_token_ttl_seconds,
            can_publish=True,
            can_subscribe=True,
        )

    async def _create_room(self, room_name: str) -> None:
        providers = self.settings.providers
        assert providers.livekit_url
        assert providers.livekit_api_key
        assert providers.livekit_api_secret
        api_url = derive_livekit_api_url(providers.livekit_url, providers.livekit_api_url)
        token = create_livekit_access_token(
            api_key=providers.livekit_api_key,
            api_secret=providers.livekit_api_secret,
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

        if self.http_client is not None:
            response = await self.http_client.post(
                f"{api_url}/twirp/livekit.RoomService/CreateRoom",
                headers=headers,
                json=payload,
                timeout=10,
            )
            self._raise_for_room_response(response)
            return

        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{api_url}/twirp/livekit.RoomService/CreateRoom",
                headers=headers,
                json=payload,
                timeout=10,
            )
        self._raise_for_room_response(response)

    def _raise_for_room_response(self, response: Any) -> None:
        status_code = getattr(response, "status_code", 200)
        if status_code < 400:
            return
        text = str(getattr(response, "text", ""))
        if status_code == 409 or (status_code == 400 and "already" in text.lower()):
            return
        raise LiveKitRoomError(f"LiveKit room creation failed with HTTP {status_code}: {text}")
