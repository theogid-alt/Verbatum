from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from verbatim.analytics.call_notes import generate_call_notes
from verbatim.analytics.latency import summarize_call_events
from verbatim.config import clear_settings_cache, get_settings, validate_runtime_selection
from verbatim.events import EventSink, load_events, new_id, normalize_event_name, safe_metadata
from verbatim.hume import HumeError, create_hume_evi_session
from verbatim.integrations.followup import twilio_sms_configured
from verbatim.integrations.nango import NangoClient, NangoError
from verbatim.integrations.store import CALENDAR_TOOL_NAMES, IntegrationStore
from verbatim.integrations.tools import verbatim_tools_ready
from verbatim.rooms import DailyRoomManager, LiveKitRoomManager, RoomError, resolve_room


ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = ROOT / "static"
CLIENT_EVENT_PREFIXES = ("browser.audio.", "livekit.client.", "hume.client.", "daily.client.")


@dataclass
class ActiveAgent:
    process: asyncio.subprocess.Process

    def done(self) -> bool:
        return self.process.returncode is not None

    def cancelled(self) -> bool:
        return False


ACTIVE_AGENT: dict[str, ActiveAgent] = {}


def create_app():
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse
    from fastapi.staticfiles import StaticFiles

    app = FastAPI(title="Verbatim V2 Voice Agent", version="0.2.0")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    @app.get("/api/health")
    async def health():
        _prune_agent()
        settings = get_settings()
        return {
            "ok": True,
            "version": "0.2.0",
            "environment": settings.agent.environment,
            "active_agents": _active_agent_count(),
        }

    @app.get("/api/config")
    async def config():
        settings = get_settings()
        return _browser_config(settings)

    @app.get("/api/integrations/catalog")
    async def integrations_catalog():
        settings = get_settings()
        return _integration_catalog(settings)

    @app.post("/api/integrations/nango/connect-session")
    async def nango_connect_session(payload: dict[str, Any] | None = None):
        settings = get_settings()
        payload = payload or {}
        client_id = _client_id_from_payload(settings, payload)
        integration_key = _integration_key(settings, payload.get("integration_key"))
        if not settings.integrations.nango_secret_key:
            raise HTTPException(status_code=400, detail="NANGO_SECRET_KEY is required to create a Nango Connect session.")
        store = _integration_store(settings)
        store.upsert_connection(
            client_id=client_id,
            provider="nango",
            integration_key=integration_key,
            connection_id=None,
            status="pending",
            allowed_tools=CALENDAR_TOOL_NAMES,
        )
        try:
            session = await NangoClient(settings).create_connect_session(
                client_id=client_id,
                integration_key=integration_key,
            )
        except NangoError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not session.get("connect_link"):
            raise HTTPException(status_code=502, detail="Nango did not return a connect_link.")
        return {
            "client_id": client_id,
            "integration_provider": "nango",
            "integration_key": integration_key,
            "connect_link": session.get("connect_link"),
            "expires_at": session.get("expires_at"),
        }

    @app.get("/api/integrations/status")
    async def integrations_status(client_id: str | None = None):
        settings = get_settings()
        resolved_client_id = _client_id_from_payload(settings, {"client_id": client_id})
        await _refresh_nango_connections(settings, client_id=resolved_client_id)
        return _integration_status(settings, client_id=resolved_client_id)

    @app.post("/api/rooms")
    async def create_room(payload: dict[str, Any] | None = None):
        _prune_agent()
        await _cancel_active_agent()
        clear_settings_cache()
        settings = _settings_from_payload(payload or {}, include_llm=False)
        if settings.providers.transport_provider == "hume_evi":
            raise HTTPException(status_code=400, detail="Hume EVI uses /api/hume/evi/session.")
        try:
            validate_runtime_selection(settings)
            call_id = new_id("call")
            session_id = new_id("sess")
            room = await resolve_room(settings, call_id=call_id, session_id=session_id)
        except (RoomError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "transport_provider": room.transport_provider,
            "room_url": room.room_url,
            "room_name": room.room_name,
            "room_token": room.room_token,
            "room_geo": room.room_geo,
            "source": room.source,
            "call_id": call_id,
            "session_id": session_id,
            "client_id": _client_id_from_payload(settings, payload or {}),
            "tools_enabled": _tools_enabled_from_payload(settings, payload or {}),
        }

    @app.post("/api/agent/start")
    async def start_agent(payload: dict[str, Any] | None = None):
        _prune_agent()
        clear_settings_cache()
        payload = payload or {}
        settings = _settings_from_payload(payload, include_llm=True)
        if settings.providers.transport_provider == "hume_evi":
            raise HTTPException(status_code=400, detail="Hume EVI runs in the browser via /api/hume/evi/session.")
        try:
            validate_runtime_selection(settings)
            if _tools_enabled_from_payload(settings, payload) and settings.providers.llm_provider == "ultravox":
                raise ValueError("Tool calling is only supported for text LLM + Cartesia cascade calls.")
            if _tools_enabled_from_payload(settings, payload):
                client_id = _client_id_from_payload(settings, payload)
                await _refresh_nango_connections(settings, client_id=client_id)
                _validate_tools_ready(settings, client_id=client_id)
            missing = settings.missing_agent_keys()
            if missing:
                raise ValueError(f"Missing required agent environment variables: {', '.join(missing)}")
            call_id = str(payload.get("call_id") or new_id("call"))
            session_id = str(payload.get("session_id") or new_id("sess"))
            room_url, room_token, room_name = _agent_room_values(settings, payload, call_id=call_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await _cancel_active_agent()
        process = await _spawn_agent_worker(
            {
                "transport_provider": settings.providers.transport_provider,
                "room_url": room_url,
                "room_token": room_token,
                "room_name": room_name,
                "call_id": call_id,
                "session_id": session_id,
                "client_id": _client_id_from_payload(settings, payload),
                "caller_phone": _caller_phone_from_payload(payload),
                "knowledge_base": _call_text_from_payload(payload, "knowledge_base", max_chars=12000),
                "tools_enabled": _tools_enabled_from_payload(settings, payload),
                "stt_provider": settings.providers.stt_provider,
                "deepgram_model": settings.providers.deepgram_model,
                "llm_provider": settings.providers.llm_provider,
                "llm_model": settings.providers.llm_model,
            }
        )
        ACTIVE_AGENT.clear()
        ACTIVE_AGENT[call_id] = ActiveAgent(process=process)
        return {
            "started": True,
            "call_id": call_id,
            "session_id": session_id,
            "transport_provider": settings.providers.transport_provider,
            "room_name": room_name,
            "stt_provider": settings.providers.stt_provider,
            "stt_model": settings.providers.deepgram_model,
            "llm_provider": settings.providers.llm_provider,
            "llm_model": settings.providers.llm_model,
            "tts_provider": "ultravox" if settings.providers.llm_provider == "ultravox" else "cartesia",
            "tts_model": settings.providers.llm_model if settings.providers.llm_provider == "ultravox" else settings.voice.cartesia_model,
            "client_id": _client_id_from_payload(settings, payload),
            "caller_phone_configured": bool(_caller_phone_from_payload(payload)),
            "knowledge_base_configured": bool(_call_text_from_payload(payload, "knowledge_base", max_chars=12000)),
            "knowledge_base_chars": len(_call_text_from_payload(payload, "knowledge_base", max_chars=12000) or ""),
            "tools_enabled": _tools_enabled_from_payload(settings, payload),
        }

    @app.post("/api/agent/stop")
    async def stop_agent(payload: dict[str, Any] | None = None):
        stopped = await _cancel_active_agent()
        return {"stopped": stopped, "active_agents": _active_agent_count()}

    @app.get("/api/agent/status")
    async def agent_status():
        _prune_agent()
        return {
            call_id: {
                "done": agent.done(),
                "cancelled": agent.cancelled(),
                "pid": agent.process.pid,
                "returncode": agent.process.returncode,
            }
            for call_id, agent in ACTIVE_AGENT.items()
        }

    @app.post("/api/hume/evi/session")
    async def hume_session(payload: dict[str, Any] | None = None):
        _prune_agent()
        await _cancel_active_agent()
        clear_settings_cache()
        payload = payload or {}
        settings = get_settings()
        call_id = new_id("call")
        session_id = new_id("sess")
        knowledge_base = _call_text_from_payload(payload, "knowledge_base", max_chars=12000)
        try:
            session = await create_hume_evi_session(
                settings,
                call_id=call_id,
                session_id=session_id,
                knowledge_base=knowledge_base,
            )
        except HumeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Hume token request failed: {exc.__class__.__name__}") from exc
        sink = _sink(settings, call_id, session_id)
        hume_config_id = settings.providers.hume_evi_config_id if settings.providers.hume_evi_use_config else None
        hume_config_version = settings.providers.hume_evi_config_version if settings.providers.hume_evi_use_config else None
        sink.emit("session.created", provider="hume_evi", metadata={"transport_provider": "hume_evi"})
        sink.emit(
            "session.configured",
            provider="hume_evi",
            metadata={
                "transport_provider": "hume_evi",
                "room_name": "hume-evi-direct",
                "stt_provider": "hume_evi",
                "stt_model": "hume-evi",
                "llm_provider": "hume_evi",
                "llm_model": "hume-evi",
                "tts_provider": "hume_evi",
                "tts_model": "hume-evi",
                "hume_evi_config_id": hume_config_id,
                "hume_evi_config_version": hume_config_version,
                "hume_evi_use_config": settings.providers.hume_evi_use_config,
                "knowledge_base_configured": bool(knowledge_base),
                "knowledge_base_chars": len(knowledge_base or ""),
            },
        )
        return session

    @app.post("/api/analytics/client-event")
    async def client_event(payload: dict[str, Any]):
        settings = get_settings()
        call_id = str(payload.get("call_id") or "").strip()
        if not call_id:
            raise HTTPException(status_code=400, detail="call_id is required.")
        event_name = normalize_event_name(str(payload.get("event_name") or "client.event"))
        if not event_name.startswith(CLIENT_EVENT_PREFIXES):
            raise HTTPException(status_code=400, detail="Unsupported client event name.")
        sink = _sink(settings, call_id, str(payload.get("session_id") or "browser"))
        metadata = safe_metadata(payload.get("metadata") or {})
        metadata["source"] = "browser"
        sink.emit(event_name, provider=str(payload.get("provider") or "browser"), metadata=metadata)
        if event_name == "hume.client.user.message":
            text = str(metadata.get("transcript") or metadata.get("text_preview") or "").strip()
            if text:
                sink.emit("transcript.user", provider="hume_evi", turn_id=new_id("turn"), metadata={"text": text})
        return {"ok": True}

    @app.get("/api/analytics/summary")
    async def analytics_summary(call_id: str | None = None):
        settings = get_settings()
        events = load_events(settings.instrumentation.event_log_path)
        selected_call_id = call_id or _latest_call_id(events)
        summary = summarize_call_events(events, call_id=selected_call_id)
        summary["latest_call_id"] = selected_call_id
        summary["active_agents"] = _active_agent_count()
        return summary

    @app.get("/api/analytics/call-notes")
    async def analytics_call_notes(call_id: str | None = None):
        settings = get_settings()
        events = load_events(settings.instrumentation.event_log_path)
        selected_call_id = call_id or _latest_call_id(events)
        return generate_call_notes(events, call_id=selected_call_id)

    @app.get("/api/analytics/transcript")
    async def analytics_transcript(call_id: str | None = None):
        settings = get_settings()
        events = load_events(settings.instrumentation.event_log_path)
        selected_call_id = call_id or _latest_call_id(events)
        transcript_path = settings.instrumentation.transcript_dir / f"{selected_call_id}.jsonl" if selected_call_id else None
        items = load_events(transcript_path) if transcript_path else []
        return {"call_id": selected_call_id, "items": items[-100:]}

    return app


app = create_app()


def _settings_from_payload(payload: dict[str, Any], *, include_llm: bool) -> Any:
    settings = get_settings()
    return settings.with_overrides(
        transport_provider=payload.get("transport_provider"),
        stt_provider=payload.get("stt_provider"),
        deepgram_model=payload.get("deepgram_model"),
        llm_provider=payload.get("llm_provider") if include_llm else None,
        llm_model=payload.get("llm_model") if include_llm else None,
        daily_geo=payload.get("daily_geo") if payload.get("daily_geo") is not None else None,
        force_create_room=payload.get("force_create_room") if payload.get("force_create_room") is not None else None,
    )


def _browser_config(settings) -> dict[str, Any]:
    return {
        "transport_provider": settings.providers.transport_provider,
        "stt_provider": settings.providers.stt_provider,
        "stt_model": settings.providers.deepgram_model,
        "llm_provider": settings.providers.llm_provider,
        "llm_model": settings.providers.llm_model,
        "tts_provider": "cartesia",
        "tts_model": settings.voice.cartesia_model,
        "cartesia_voice_configured": bool(settings.voice.cartesia_voice_id),
        "hume_evi_configured": bool(settings.providers.hume_api_key and settings.providers.hume_secret_key),
        "default_client_id": settings.integrations.default_client_id,
        "tools_enabled": settings.integrations.tools_enabled,
        "tool_timeout_ms": settings.integrations.tool_timeout_ms,
        "caller_phone": "",
        "knowledge_base": "",
        "direct_tools_configured": followup_tools_ready_for_browser(settings),
        "integration_catalog": _integration_catalog(settings),
        "transport_options": [
            {"id": "livekit", "label": "LiveKit", "transport_provider": "livekit"},
            {"id": "daily", "label": "Daily", "transport_provider": "daily"},
            {"id": "hume_evi", "label": "Hume EVI", "transport_provider": "hume_evi"},
        ],
        "stt_options": [
            {"id": "nova_3_general", "label": "Nova-3", "stt_provider": "deepgram", "deepgram_model": "nova-3-general"},
            {"id": "deepgram_flux", "label": "Flux", "stt_provider": "deepgram_flux", "deepgram_model": "flux-general-en"},
        ],
        "llm_options": [
            {"id": "groq", "label": "Groq LLaMA 3.1 8B", "llm_provider": "groq", "llm_model": settings.providers.groq_model},
            {"id": "gemini", "label": "Gemini 2.5 Flash", "llm_provider": "gemini", "llm_model": settings.providers.gemini_model},
            {"id": "openai", "label": "OpenAI GPT-4o mini", "llm_provider": "openai", "llm_model": settings.providers.openai_model},
            {"id": "qwen", "label": f"Qwen · {settings.providers.qwen_model}", "llm_provider": "qwen", "llm_model": settings.providers.qwen_model},
            {"id": "xai", "label": "xAI Grok Fast", "llm_provider": "xai", "llm_model": settings.providers.xai_model},
            {"id": "ultravox", "label": "UltraVox Realtime", "llm_provider": "ultravox", "llm_model": settings.providers.ultravox_model},
            {"id": "mock", "label": "Mock immediate", "llm_provider": "mock", "llm_model": "mock-immediate"},
        ],
        "daily_geo": settings.providers.daily_geo,
        "daily_region_options": [
            {"id": "auto", "label": "Auto", "daily_geo": None},
            {"id": "eu-central-1", "label": "Frankfurt", "daily_geo": "eu-central-1"},
            {"id": "eu-west-2", "label": "London", "daily_geo": "eu-west-2"},
        ],
    }


def _integration_catalog(settings) -> dict[str, Any]:
    integration_key = settings.integrations.nango_google_calendar_integration_id
    direct_tools = []
    if twilio_sms_configured(settings):
        direct_tools.append("send_sms_followup")
    return {
        "providers": [
            {
                "id": "nango",
                "label": "Nango",
                "configured": bool(settings.integrations.nango_secret_key),
                "integrations": [
                    {
                        "integration_key": integration_key,
                        "label": "Google Calendar",
                        "status": "available" if settings.integrations.nango_secret_key else "needs_nango_secret",
                        "allowed_tools": CALENDAR_TOOL_NAMES,
                    }
                ],
            },
            {
                "id": "direct",
                "label": "Direct APIs",
                "configured": bool(direct_tools),
                "integrations": [
                    {
                        "integration_key": "twilio-messaging",
                        "label": "Twilio SMS",
                        "status": "available" if twilio_sms_configured(settings) else "needs_twilio_keys",
                        "allowed_tools": ["send_sms_followup"] if twilio_sms_configured(settings) else [],
                    },
                ],
            },
        ],
        "default_client_id": settings.integrations.default_client_id,
        "tools_enabled": settings.integrations.tools_enabled,
    }


def _integration_store(settings) -> IntegrationStore:
    return IntegrationStore(settings.integrations.integrations_db_path)


def _integration_key(settings, value: Any | None = None) -> str:
    return str(value or settings.integrations.nango_google_calendar_integration_id).strip()


def _client_id_from_payload(settings, payload: dict[str, Any]) -> str:
    return str(payload.get("client_id") or settings.integrations.default_client_id).strip() or "demo"


def _caller_phone_from_payload(payload: dict[str, Any]) -> str | None:
    value = str(payload.get("caller_phone") or "").strip()
    return value or None


def _call_text_from_payload(payload: dict[str, Any], key: str, *, max_chars: int) -> str | None:
    value = str(payload.get(key) or "").strip()
    if not value:
        return None
    return value[:max_chars]


def _tools_enabled_from_payload(settings, payload: dict[str, Any]) -> bool:
    if "tools_enabled" not in payload or payload.get("tools_enabled") is None:
        return bool(settings.integrations.tools_enabled)
    value = payload.get("tools_enabled")
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _validate_tools_ready(settings, *, client_id: str) -> None:
    if not verbatim_tools_ready(settings, client_id=client_id):
        raise ValueError(
            "No Verbatim tools are ready. Connect Google Calendar through Nango or configure Twilio SMS in .env."
        )


def followup_tools_ready_for_browser(settings) -> bool:
    return twilio_sms_configured(settings)


async def _refresh_nango_connections(settings, *, client_id: str) -> None:
    if not settings.integrations.nango_secret_key:
        return
    integration_key = settings.integrations.nango_google_calendar_integration_id
    store = _integration_store(settings)
    try:
        connections = await NangoClient(settings).list_connections(client_id=client_id, integration_key=integration_key)
    except NangoError:
        return
    for connection in connections:
        if not connection.connection_id:
            continue
        store.upsert_connection(
            client_id=client_id,
            provider="nango",
            integration_key=integration_key,
            connection_id=connection.connection_id,
            status=connection.status or "connected",
            allowed_tools=CALENDAR_TOOL_NAMES,
        )


def _integration_status(settings, *, client_id: str) -> dict[str, Any]:
    store = _integration_store(settings)
    connections = store.list_connections(client_id=client_id)
    if not connections:
        integration_key = settings.integrations.nango_google_calendar_integration_id
        connections = [
            store.upsert_connection(
                client_id=client_id,
                provider="nango",
                integration_key=integration_key,
                connection_id=None,
                status="not_connected",
                allowed_tools=CALENDAR_TOOL_NAMES,
            )
        ]
    return {
        "client_id": client_id,
        "integrations": [
            {
                "provider": connection.provider,
                "integration_key": connection.integration_key,
                "connection_id": connection.connection_id,
                "status": connection.status,
                "allowed_tools": connection.allowed_tools,
                "created_at": connection.created_at,
                "updated_at": connection.updated_at,
            }
            for connection in connections
        ],
    }


def _agent_room_values(settings, payload: dict[str, Any], *, call_id: str) -> tuple[str, str | None, str | None]:
    room_url = str(payload.get("room_url") or "").strip()
    room_name = str(payload.get("room_name") or "").strip() or None
    if settings.providers.transport_provider == "livekit":
        if not room_url:
            room_url = settings.providers.livekit_url or ""
        if not room_name:
            raise ValueError("room_name is required for LiveKit.")
        room_token = LiveKitRoomManager(settings).bot_token(room_name=room_name, call_id=call_id)
        return room_url, room_token, room_name
    room_token = str(payload.get("room_token") or settings.providers.daily_room_token or "").strip() or None
    if not room_url:
        room_url = settings.providers.daily_room_url or ""
    return room_url, room_token, room_name


async def _spawn_agent_worker(payload: dict[str, Any]) -> asyncio.subprocess.Process:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "verbatim.agent_worker",
        cwd=str(ROOT),
        env=env,
        stdin=asyncio.subprocess.PIPE,
    )
    if process.stdin is None:
        raise RuntimeError("Agent worker stdin is unavailable.")
    process.stdin.write(json.dumps(payload).encode("utf-8"))
    await process.stdin.drain()
    process.stdin.close()
    if hasattr(process.stdin, "wait_closed"):
        await process.stdin.wait_closed()
    return process


async def _cancel_active_agent() -> bool:
    if not ACTIVE_AGENT:
        return False
    agents = list(ACTIVE_AGENT.values())
    ACTIVE_AGENT.clear()
    stopped = False
    for agent in agents:
        if agent.done():
            stopped = True
            continue
        agent.process.terminate()
        stopped = True
    for agent in agents:
        if agent.done():
            continue
        try:
            await asyncio.wait_for(agent.process.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            agent.process.kill()
            await agent.process.wait()
    return stopped


def _prune_agent() -> None:
    for call_id, agent in list(ACTIVE_AGENT.items()):
        if agent.done():
            ACTIVE_AGENT.pop(call_id, None)


def _active_agent_count() -> int:
    _prune_agent()
    return len(ACTIVE_AGENT)


def _sink(settings, call_id: str, session_id: str) -> EventSink:
    return EventSink(
        settings.instrumentation.event_log_path,
        settings.instrumentation.transcript_dir,
        settings.instrumentation.call_summary_dir,
        session_id=session_id,
        call_id=call_id,
        agent_id=settings.agent.agent_id,
        client_id=settings.agent.client_id,
        enabled=settings.instrumentation.enable_jsonl_events,
    )


def _latest_call_id(events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        if event.get("call_id"):
            return str(event["call_id"])
    return None


def main() -> None:
    import uvicorn

    uvicorn.run("verbatim.server:create_app", factory=True, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
