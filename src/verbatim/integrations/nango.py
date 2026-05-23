from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from verbatim.config import Settings


class NangoError(RuntimeError):
    pass


@dataclass(frozen=True)
class NangoConnection:
    connection_id: str
    provider_config_key: str
    provider: str | None = None
    status: str = "connected"
    tags: dict[str, Any] | None = None


class NangoClient:
    def __init__(self, settings: Settings, *, http_client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.base_url = settings.integrations.nango_api_base_url.rstrip("/")
        self.secret_key = settings.integrations.nango_secret_key
        self._http_client = http_client

    def is_configured(self) -> bool:
        return bool(self.secret_key)

    async def create_connect_session(self, *, client_id: str, integration_key: str) -> dict[str, Any]:
        self._require_secret()
        payload = {
            "tags": {
                "client_id": client_id,
                "end_user_id": client_id,
                "verbatim_client_id": client_id,
            },
            "allowed_integrations": [integration_key],
        }
        data = await self._request("POST", "/connect/sessions", json=payload, expected=(200, 201))
        session = _unwrap_data(data)
        return {
            "connect_link": session.get("connect_link"),
            "expires_at": session.get("expires_at"),
        }

    async def get_connection(self, *, connection_id: str, integration_key: str) -> NangoConnection | None:
        self._require_secret()
        data = await self._request(
            "GET",
            f"/connections/{connection_id}",
            params={"provider_config_key": integration_key},
            expected=(200, 404),
        )
        if not data or data.get("status_code") == 404:
            return None
        payload = _unwrap_data(data)
        return _connection_from_payload(payload)

    async def list_connections(self, *, client_id: str, integration_key: str) -> list[NangoConnection]:
        self._require_secret()
        candidates = [
            ("/connections", {"tags[client_id]": client_id, "limit": 100}),
            ("/connections", {"tags[end_user_id]": client_id, "limit": 100}),
            ("/connections", {"tags[verbatim_client_id]": client_id, "limit": 100}),
            ("/connections", {"limit": 100}),
        ]
        for path, params in candidates:
            try:
                data = await self._request("GET", path, params=params, expected=(200, 404))
            except NangoError:
                continue
            connections = [_connection_from_payload(item) for item in _connection_items(data)]
            matches = [
                connection
                for connection in connections
                if connection.provider_config_key == integration_key
                and _connection_matches_client(connection, client_id)
            ]
            if matches:
                return matches
        return []

    async def google_calendar_freebusy(
        self,
        *,
        connection_id: str,
        integration_key: str,
        time_min: str,
        time_max: str,
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        return await self.proxy(
            "POST",
            "/calendar/v3/freeBusy",
            connection_id=connection_id,
            integration_key=integration_key,
            json={
                "timeMin": time_min,
                "timeMax": time_max,
                "items": [{"id": calendar_id}],
            },
        )

    async def google_calendar_create_event(
        self,
        *,
        connection_id: str,
        integration_key: str,
        title: str,
        start_iso: str,
        end_iso: str,
        timezone: str,
        attendee_email: str | None = None,
        notes: str | None = None,
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "summary": title,
            "description": notes or "Created by Verbatim after user confirmation.",
            "start": {"dateTime": start_iso, "timeZone": timezone},
            "end": {"dateTime": end_iso, "timeZone": timezone},
        }
        if attendee_email:
            body["attendees"] = [{"email": attendee_email}]
        return await self.proxy(
            "POST",
            f"/calendar/v3/calendars/{calendar_id}/events",
            connection_id=connection_id,
            integration_key=integration_key,
            json=body,
        )

    async def google_calendar_delete_event(
        self,
        *,
        connection_id: str,
        integration_key: str,
        event_id: str,
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        safe_calendar_id = quote(calendar_id, safe="")
        safe_event_id = quote(event_id, safe="")
        return await self.proxy(
            "DELETE",
            f"/calendar/v3/calendars/{safe_calendar_id}/events/{safe_event_id}",
            connection_id=connection_id,
            integration_key=integration_key,
        )

    async def proxy(
        self,
        method: str,
        path: str,
        *,
        connection_id: str,
        integration_key: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_secret()
        proxy_path = path if path.startswith("/") else f"/{path}"
        return await self._request(
            method,
            f"/proxy{proxy_path}",
            headers={
                "Connection-Id": connection_id,
                "Provider-Config-Key": integration_key,
            },
            json=json,
            params=params,
            expected=tuple(range(200, 300)),
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> dict[str, Any]:
        self._require_secret()
        request_headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
            **(headers or {}),
        }
        client = self._http_client
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(timeout=10.0)
        try:
            response = await client.request(
                method,
                f"{self.base_url}{path}",
                headers=request_headers,
                json=json,
                params=params,
            )
        except httpx.TimeoutException as exc:
            raise NangoError("Nango request timed out.") from exc
        except httpx.HTTPError as exc:
            raise NangoError(f"Nango request failed: {exc.__class__.__name__}") from exc
        finally:
            if owns_client:
                await client.aclose()
        if response.status_code not in expected:
            detail = response.text[:240] if response.text else response.reason_phrase
            raise NangoError(f"Nango HTTP {response.status_code}: {detail}")
        if response.status_code == 404:
            return {"status_code": 404}
        try:
            return response.json()
        except ValueError:
            return {}

    def _require_secret(self) -> None:
        if not self.secret_key:
            raise NangoError("NANGO_SECRET_KEY is not configured.")


def _unwrap_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _connection_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    for key in ("connections", "items", "records"):
        items = payload.get(key)
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    if payload.get("connection_id"):
        return [payload]
    return []


def _connection_from_payload(payload: dict[str, Any]) -> NangoConnection:
    provider_config_key = payload.get("provider_config_key") or payload.get("providerConfigKey") or payload.get("integration_id")
    connection_id = payload.get("connection_id") or payload.get("connectionId") or payload.get("id")
    status = payload.get("status") or ("error" if payload.get("errors") else "connected")
    return NangoConnection(
        connection_id=str(connection_id or ""),
        provider_config_key=str(provider_config_key or ""),
        provider=payload.get("provider"),
        status=str(status),
        tags=payload.get("tags") if isinstance(payload.get("tags"), dict) else {},
    )


def _connection_matches_client(connection: NangoConnection, client_id: str) -> bool:
    tags = connection.tags or {}
    values = {
        str(tags.get("client_id") or ""),
        str(tags.get("end_user_id") or ""),
        str(tags.get("verbatim_client_id") or ""),
    }
    return client_id in values


def parse_iso_datetime(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    return datetime.fromisoformat(text)
