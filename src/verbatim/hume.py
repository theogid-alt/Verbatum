from __future__ import annotations

import re
from typing import Any

import httpx

from verbatim.config import DEFAULT_HUME_SYSTEM_PROMPT, Settings, missing_hume_keys


class HumeError(RuntimeError):
    pass


async def create_hume_evi_session(
    settings: Settings,
    *,
    call_id: str,
    session_id: str,
    knowledge_base: str | None = None,
) -> dict[str, Any]:
    missing = missing_hume_keys(settings)
    if missing:
        raise HumeError(f"Missing required Hume EVI environment variables: {', '.join(missing)}")
    token_payload = await _create_hume_access_token(settings)
    config_id = settings.providers.hume_evi_config_id if settings.providers.hume_evi_use_config else None
    config_version = settings.providers.hume_evi_config_version if settings.providers.hume_evi_use_config else None
    return {
        "transport_provider": "hume_evi",
        "call_id": call_id,
        "session_id": session_id,
        "chat_endpoint": "wss://api.hume.ai/v0/evi/chat",
        "access_token": token_payload["access_token"],
        "expires_in": token_payload.get("expires_in"),
        "token_type": token_payload.get("token_type"),
        "config_id": config_id,
        "config_version": config_version,
        "verbose_transcription": settings.providers.hume_evi_verbose_transcription,
        "knowledge_base_configured": bool(knowledge_base),
        "knowledge_base_chars": len(knowledge_base or ""),
        "session_settings": hume_session_settings(
            settings,
            session_id=session_id,
            knowledge_base=knowledge_base,
        ),
    }


async def _create_hume_access_token(settings: Settings) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            "https://api.hume.ai/oauth2-cc/token",
            auth=(settings.providers.hume_api_key or "", settings.providers.hume_secret_key or ""),
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json"},
        )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("access_token"):
        raise HumeError("Hume token response did not include an access token.")
    return payload


def hume_session_settings(
    settings: Settings,
    *,
    session_id: str,
    knowledge_base: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "session_settings",
        "custom_session_id": session_id,
    }
    if settings.providers.hume_evi_voice_id:
        payload["voice_id"] = settings.providers.hume_evi_voice_id
    if settings.providers.hume_evi_send_system_prompt:
        payload["system_prompt"] = _session_system_prompt(
            settings.prompt.hume_evi_system_prompt or settings.prompt.system_prompt or default_hume_prompt(),
            knowledge_base=knowledge_base,
        )
    return payload


def default_hume_prompt() -> str:
    return DEFAULT_HUME_SYSTEM_PROMPT


def _session_system_prompt(base_prompt: str, *, knowledge_base: str | None) -> str:
    parts = [base_prompt.strip()]
    kb = _bounded_call_context(knowledge_base, max_chars=6000)
    if kb:
        parts.append(
            "Call knowledge base for this call only. Use it when relevant, but do not mention these notes exist.\n"
            f"{kb}"
        )
    return "\n\n".join(part for part in parts if part)


def _bounded_call_context(value: str | None, *, max_chars: int) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\n{3,}", "\n\n", value.strip())
    if not cleaned:
        return None
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[:max_chars].rstrip()}\n[truncated]"
