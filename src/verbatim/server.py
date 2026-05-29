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

import httpx

from verbatim.analytics.call_notes import generate_call_notes
from verbatim.analytics.evaluation import (
    build_call_evaluation_context,
    load_rubric,
    save_call_evaluation,
    summarize_evaluations,
)
from verbatim.analytics.latency import summarize_call_events
from verbatim.client_config import ClientConfig, ClientConfigStore, integration_definitions
from verbatim.config import clear_settings_cache, get_settings, validate_runtime_selection
from verbatim.events import EventSink, load_events, new_id, normalize_event_name, safe_metadata
from verbatim.hume import HumeError, create_hume_evi_session
from verbatim.integrations.followup import twilio_sms_configured
from verbatim.integrations.nango import NangoClient, NangoError
from verbatim.integrations.store import IntegrationStore
from verbatim.integrations.tools import followup_tool_names, scheduling_tool_names
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

    app = FastAPI(title="Verbatim V2 Voice Agent", version="0.3.2")
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
            "version": "0.3.2",
            "environment": settings.agent.environment,
            "active_agents": _active_agent_count(),
        }

    @app.get("/api/config")
    async def config():
        settings = get_settings()
        return _browser_config(settings)

    @app.get("/api/client-config")
    async def client_config():
        settings = get_settings()
        return _client_config_response(settings)

    @app.put("/api/client-config/profile")
    async def update_client_profile(payload: dict[str, Any]):
        settings = get_settings()
        profile = _client_store().update_profile(settings, payload or {})
        clear_settings_cache()
        return _client_config_response(get_settings(), profile_override=profile)

    @app.put("/api/client-config/prompt")
    async def update_client_prompt(payload: dict[str, Any]):
        settings = get_settings()
        content = str((payload or {}).get("content") or "")
        _client_store().update_prompt(settings, content)
        clear_settings_cache()
        return _client_config_response(get_settings())

    @app.put("/api/client-config/kb")
    async def update_client_kb(payload: dict[str, Any]):
        settings = get_settings()
        content = str((payload or {}).get("content") or "")
        _client_store().update_kb(settings, content)
        return _client_config_response(settings)

    @app.post("/api/client-config/reset")
    async def reset_client_profile_prompt_kb():
        settings = get_settings()
        reset_config = _client_store().reset_profile_prompt_kb(settings)
        clear_settings_cache()
        return _client_config_payload(get_settings(), client_config=reset_config)

    @app.put("/api/client-config/integrations")
    async def update_client_integrations(payload: dict[str, Any]):
        settings = get_settings()
        _client_store().update_integrations(settings, payload or {})
        return _client_config_response(settings)

    @app.get("/api/integrations/catalog")
    async def integrations_catalog():
        settings = get_settings()
        return _integration_catalog(settings)

    @app.post("/api/integrations/{integration_id}/test")
    async def integration_test(integration_id: str):
        settings = get_settings()
        client_config = _client_config(settings)
        client_id = client_config.profile_id
        await _refresh_nango_connections(settings, client_id=client_id)
        cards = _integration_cards(settings, client_config=client_config, client_id=client_id)
        card = next((item for item in cards if item["id"] == integration_id), None)
        if not card:
            raise HTTPException(status_code=404, detail=f"Unknown integration: {integration_id}")
        if not card["implemented"]:
            return {"ok": False, "integration_id": integration_id, "status": "coming_soon", "message": "This adapter is not implemented yet."}
        if not card["enabled"]:
            return {"ok": False, "integration_id": integration_id, "status": "disabled", "message": "This integration is disabled locally."}
        if not card["ready"]:
            return {
                "ok": False,
                "integration_id": integration_id,
                "status": card["status"],
                "message": card["status_label"],
                "required_env": card["required_env"],
            }
        if card["provider"] == "webhook":
            return await _test_webhook_integration(settings, integration_id=integration_id, card=card)
        return {"ok": True, "integration_id": integration_id, "status": card["status"], "message": f"{card['label']} is ready."}

    @app.post("/api/integrations/{integration_id}/disconnect")
    async def integration_disconnect(integration_id: str):
        settings = get_settings()
        client_config = _client_config(settings)
        definition = next((item for item in integration_definitions(settings) if item["id"] == integration_id), None)
        if not definition:
            raise HTTPException(status_code=404, detail=f"Unknown integration: {integration_id}")
        _client_store().disconnect_integration(settings, integration_id)
        if definition["provider"] == "nango":
            _integration_store(settings).delete_connection(
                client_id=client_config.profile_id,
                provider="nango",
                integration_key=definition["integration_key"],
            )
        return _client_config_response(settings)

    @app.post("/api/integrations/nango/connect-session")
    async def nango_connect_session(payload: dict[str, Any] | None = None):
        settings = get_settings()
        payload = payload or {}
        client_config = _client_config(settings)
        client_id = _client_id_from_payload(settings, payload, client_config=client_config)
        definition = _integration_definition_from_payload(settings, payload)
        if not definition or definition.get("provider") != "nango":
            raise HTTPException(status_code=400, detail="This integration does not use Nango Connect.")
        integration_key = str(definition["integration_key"])
        if not settings.integrations.nango_secret_key:
            raise HTTPException(status_code=400, detail="NANGO_SECRET_KEY is required to create a Nango Connect session.")
        store = _integration_store(settings)
        _client_store().update_integrations(settings, {"integrations": {definition["id"]: {"enabled": True}}})
        store.upsert_connection(
            client_id=client_id,
            provider="nango",
            integration_key=integration_key,
            connection_id=None,
            status="pending",
            allowed_tools=list(definition.get("allowed_tools") or []),
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
            "integration_id": definition["id"],
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
        client_config = _client_config(settings)
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
            "client_id": _client_id_from_payload(settings, payload or {}, client_config=client_config),
            "tools_enabled": _effective_tools_enabled(settings, payload or {}, client_config=client_config),
        }

    @app.post("/api/agent/start")
    async def start_agent(payload: dict[str, Any] | None = None):
        _prune_agent()
        clear_settings_cache()
        payload = payload or {}
        settings = _settings_from_payload(payload, include_llm=True)
        client_config = _client_config(settings)
        client_id = _client_id_from_payload(settings, payload, client_config=client_config)
        enabled_tools = _enabled_tool_names(settings, client_config=client_config, client_id=client_id)
        requested_tools_enabled = _tools_enabled_from_payload(settings, payload)
        tools_enabled = requested_tools_enabled and bool(enabled_tools)
        if settings.providers.transport_provider == "hume_evi":
            raise HTTPException(status_code=400, detail="Hume EVI runs in the browser via /api/hume/evi/session.")
        try:
            validate_runtime_selection(settings)
            if requested_tools_enabled and settings.providers.llm_provider == "ultravox":
                raise ValueError("Tool calling is only supported for text LLM + Cartesia cascade calls.")
            if requested_tools_enabled:
                await _refresh_nango_connections(settings, client_id=client_id)
                enabled_tools = _enabled_tool_names(settings, client_config=_client_config(settings), client_id=client_id)
                _validate_tools_ready(enabled_tools)
                tools_enabled = bool(enabled_tools)
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
                "client_id": client_id,
                "caller_phone": _caller_phone_from_payload(payload),
                "knowledge_base": _effective_knowledge_base(settings, payload, client_config=client_config),
                "system_prompt": _effective_system_prompt(
                    settings,
                    payload,
                    client_config=client_config,
                    tools_enabled=tools_enabled,
                    enabled_tools=enabled_tools if tools_enabled else [],
                ),
                "enabled_tools": enabled_tools if tools_enabled else [],
                "tools_enabled": tools_enabled,
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
            "client_id": client_id,
            "caller_phone_configured": bool(_caller_phone_from_payload(payload)),
            "knowledge_base_configured": bool(_effective_knowledge_base(settings, payload, client_config=client_config)),
            "knowledge_base_chars": len(_effective_knowledge_base(settings, payload, client_config=client_config) or ""),
            "tools_enabled": tools_enabled,
            "enabled_tools": enabled_tools if tools_enabled else [],
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
        client_config = _client_config(settings)
        call_id = new_id("call")
        session_id = new_id("sess")
        knowledge_base = _effective_knowledge_base(settings, payload, client_config=client_config)
        try:
            session = await create_hume_evi_session(
                settings,
                call_id=call_id,
                session_id=session_id,
                knowledge_base=knowledge_base,
                system_prompt=_effective_hume_system_prompt(settings, payload, client_config=client_config),
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

    @app.get("/api/evaluations/rubric")
    async def evaluations_rubric():
        return load_rubric()

    @app.get("/api/evaluations/call")
    async def evaluations_call(call_id: str | None = None, bot_version: str | None = None):
        settings = get_settings()
        events = load_events(settings.instrumentation.event_log_path)
        selected_call_id = call_id or _latest_call_id(events)
        return build_call_evaluation_context(settings, events, call_id=selected_call_id, bot_version=bot_version)

    @app.put("/api/evaluations/call/{call_id}")
    async def evaluations_save_call(call_id: str, payload: dict[str, Any]):
        settings = get_settings()
        events = load_events(settings.instrumentation.event_log_path)
        return save_call_evaluation(settings, events, call_id=call_id, payload=payload or {})

    @app.get("/api/evaluations/summary")
    async def evaluations_summary():
        settings = get_settings()
        events = load_events(settings.instrumentation.event_log_path)
        return summarize_evaluations(settings, events)

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
    client_config = _client_config(settings)
    profile = client_config.profile
    return {
        "transport_provider": profile.get("transport_provider") or settings.providers.transport_provider,
        "stt_provider": profile.get("stt_provider") or settings.providers.stt_provider,
        "stt_model": profile.get("deepgram_model") or settings.providers.deepgram_model,
        "llm_provider": profile.get("llm_provider") or settings.providers.llm_provider,
        "llm_model": profile.get("llm_model") or settings.providers.llm_model,
        "tts_provider": "cartesia",
        "tts_model": settings.voice.cartesia_model,
        "cartesia_voice_configured": bool(settings.voice.cartesia_voice_id),
        "hume_evi_configured": bool(settings.providers.hume_api_key and settings.providers.hume_secret_key),
        "default_client_id": client_config.profile_id,
        "tools_enabled": settings.integrations.tools_enabled,
        "tool_timeout_ms": settings.integrations.tool_timeout_ms,
        "caller_phone": "",
        "knowledge_base": client_config.knowledge_base,
        "client_config": _client_config_payload(settings, client_config=client_config),
        "direct_tools_configured": followup_tools_ready_for_browser(settings),
        "integration_catalog": _integration_catalog(settings, client_config=client_config),
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


def _integration_catalog(settings, *, client_config: ClientConfig | None = None) -> dict[str, Any]:
    client_config = client_config or _client_config(settings)
    cards = _integration_cards(settings, client_config=client_config, client_id=client_config.profile_id)
    calendar = next((card for card in cards if card["id"] == "google_calendar"), None)
    twilio = next((card for card in cards if card["id"] == "twilio_sms"), None)
    return {
        "cards": cards,
        "providers": [
            {
                "id": "nango",
                "label": "Nango",
                "configured": bool(settings.integrations.nango_secret_key),
                "integrations": [
                    {
                        "integration_key": settings.integrations.nango_google_calendar_integration_id,
                        "label": "Google Calendar",
                        "status": calendar["status"] if calendar else "not_connected",
                        "allowed_tools": calendar["allowed_tools"] if calendar and calendar["enabled"] else [],
                    }
                ],
            },
            {
                "id": "direct",
                "label": "Direct APIs",
                "configured": bool(twilio and twilio["ready"]),
                "integrations": [
                    {
                        "integration_key": "twilio-messaging",
                        "label": "Twilio SMS",
                        "status": twilio["status"] if twilio else "missing_env",
                        "allowed_tools": twilio["allowed_tools"] if twilio and twilio["enabled"] and twilio["ready"] else [],
                    },
                ],
            },
        ],
        "default_client_id": client_config.profile_id,
        "tools_enabled": settings.integrations.tools_enabled,
    }


def _integration_store(settings) -> IntegrationStore:
    return IntegrationStore(settings.integrations.integrations_db_path)


def _client_store() -> ClientConfigStore:
    return ClientConfigStore()


def _client_config(settings) -> ClientConfig:
    return _client_store().read(settings)


def _client_config_response(settings, *, profile_override: dict[str, Any] | None = None) -> dict[str, Any]:
    client_config = _client_config(settings)
    if profile_override is not None:
        client_config = ClientConfig(
            profile=profile_override,
            prompt=client_config.prompt,
            knowledge_base=client_config.knowledge_base,
            integrations=client_config.integrations,
        )
    return _client_config_payload(settings, client_config=client_config)


def _client_config_payload(settings, *, client_config: ClientConfig) -> dict[str, Any]:
    return {
        "profile": client_config.profile,
        "prompt": {"content": client_config.prompt, "configured": bool(client_config.prompt.strip())},
        "knowledge_base": {
            "content": client_config.knowledge_base,
            "configured": bool(client_config.knowledge_base.strip()),
            "chars": len(client_config.knowledge_base or ""),
        },
        "integrations": client_config.integrations,
        "integration_catalog": _integration_catalog(settings, client_config=client_config),
    }


def _integration_key(settings, value: Any | None = None) -> str:
    return str(value or settings.integrations.nango_google_calendar_integration_id).strip()


def _integration_definition_from_payload(settings, payload: dict[str, Any]) -> dict[str, Any] | None:
    integration_id = str(payload.get("integration_id") or "").strip()
    integration_key = str(payload.get("integration_key") or "").strip()
    definitions = integration_definitions(settings)
    if integration_id:
        match = next((item for item in definitions if item["id"] == integration_id), None)
        if match:
            return match
    if integration_key:
        return next((item for item in definitions if item["integration_key"] == integration_key), None)
    return next((item for item in definitions if item["id"] == "google_calendar"), None)


def _client_id_from_payload(settings, payload: dict[str, Any], *, client_config: ClientConfig | None = None) -> str:
    client_config = client_config or _client_config(settings)
    return str(payload.get("client_id") or client_config.profile_id or settings.integrations.default_client_id).strip() or "demo"


def _caller_phone_from_payload(payload: dict[str, Any]) -> str | None:
    value = str(payload.get("caller_phone") or "").strip()
    return value or None


def _call_text_from_payload(payload: dict[str, Any], key: str, *, max_chars: int) -> str | None:
    value = str(payload.get(key) or "").strip()
    if not value:
        return None
    return value[:max_chars]


def _effective_knowledge_base(settings, payload: dict[str, Any], *, client_config: ClientConfig | None = None) -> str | None:
    override = _call_text_from_payload(payload, "knowledge_base", max_chars=12000)
    if override:
        return override
    client_config = client_config or _client_config(settings)
    value = (client_config.knowledge_base or "").strip()
    return value[:12000] or None


def _effective_system_prompt(
    settings,
    payload: dict[str, Any],
    *,
    client_config: ClientConfig | None = None,
    tools_enabled: bool = False,
    enabled_tools: list[str] | None = None,
) -> str:
    override = _call_text_from_payload(payload, "system_prompt", max_chars=12000)
    client_config = client_config or _client_config(settings)
    prompt = (override or client_config.prompt or settings.prompt.system_prompt).strip() or settings.prompt.system_prompt
    return _compose_agent_system_prompt(
        prompt,
        client_config=client_config,
        tools_enabled=tools_enabled,
        enabled_tools=enabled_tools,
    )


def _effective_hume_system_prompt(settings, payload: dict[str, Any], *, client_config: ClientConfig | None = None) -> str:
    override = _call_text_from_payload(payload, "system_prompt", max_chars=12000)
    client_config = client_config or _client_config(settings)
    prompt = override or client_config.prompt.strip() or settings.prompt.hume_evi_system_prompt or settings.prompt.system_prompt
    return _compose_agent_system_prompt(prompt, client_config=client_config)


def _compose_agent_system_prompt(
    prompt: str,
    *,
    client_config: ClientConfig,
    tools_enabled: bool = False,
    enabled_tools: list[str] | None = None,
) -> str:
    parts = [prompt.strip()]
    profile_context = _client_profile_prompt_context(client_config)
    if profile_context:
        parts.append(profile_context)
    if tools_enabled:
        parts.append(_tool_truth_prompt(enabled_tools or []))
    return "\n\n".join(part for part in parts if part)


def _client_profile_prompt_context(client_config: ClientConfig) -> str:
    profile = client_config.profile or {}
    assistant_name = str(profile.get("assistant_name") or "").strip()
    business_name = str(profile.get("business_name") or "").strip()
    industry = str(profile.get("industry") or "").strip()
    timezone = str(profile.get("timezone") or "").strip()
    lines = []
    if assistant_name:
        lines.append(f"Assistant name: {assistant_name}.")
    if business_name:
        lines.append(f"Business name: {business_name}.")
    if industry:
        lines.append(f"Industry: {industry}.")
    if timezone:
        lines.append(f"Timezone: {timezone}.")
    if not lines:
        return ""
    lines.append("Use this identity only when useful; do not invent a city, company, or caller intent.")
    return "Saved client profile:\n" + "\n".join(lines)


def _tool_truth_prompt(enabled_tools: list[str]) -> str:
    tool_list = ", ".join(sorted(set(enabled_tools))) or "none"
    return (
        "Tool truth rules:\n"
        f"Enabled tools: {tool_list}.\n"
        "Never claim availability, booking, deletion, or SMS success from memory or intention.\n"
        "Only say a tool action succeeded after the tool result says it succeeded.\n"
        "If the calendar or SMS tool is unavailable or fails, say that directly and offer follow-up."
    )


def _tools_enabled_from_payload(settings, payload: dict[str, Any]) -> bool:
    if "tools_enabled" not in payload or payload.get("tools_enabled") is None:
        return bool(settings.integrations.tools_enabled)
    value = payload.get("tools_enabled")
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _effective_tools_enabled(settings, payload: dict[str, Any], *, client_config: ClientConfig | None = None) -> bool:
    if not _tools_enabled_from_payload(settings, payload):
        return False
    client_config = client_config or _client_config(settings)
    client_id = _client_id_from_payload(settings, payload, client_config=client_config)
    return bool(_enabled_tool_names(settings, client_config=client_config, client_id=client_id))


def _validate_tools_ready(enabled_tools: list[str]) -> None:
    if not enabled_tools:
        raise ValueError(
            "No enabled Verbatim tools are ready. Connect Google Calendar through Nango, enable an integration card, or configure Twilio SMS in .env."
        )


def followup_tools_ready_for_browser(settings) -> bool:
    return twilio_sms_configured(settings)


def _integration_cards(settings, *, client_config: ClientConfig, client_id: str) -> list[dict[str, Any]]:
    integration_state = client_config.integrations.get("integrations") or {}
    store = _integration_store(settings)
    cards: list[dict[str, Any]] = []
    for definition in integration_definitions(settings):
        state = integration_state.get(definition["id"], {})
        enabled = bool(state.get("enabled")) if definition["implemented"] else False
        status = "coming_soon"
        status_label = "Coming soon"
        ready = False
        connection_id = None
        missing_env: list[str] = []
        if definition["implemented"]:
            if not enabled:
                status = "disabled"
                status_label = "Disabled locally"
            elif definition["provider"] == "nango":
                if not settings.integrations.nango_secret_key:
                    status = "missing_env"
                    status_label = "Add NANGO_SECRET_KEY to .env"
                    missing_env = ["NANGO_SECRET_KEY"]
                else:
                    connection = store.get_connection(
                        client_id=client_id,
                        provider="nango",
                        integration_key=definition["integration_key"],
                    )
                    connection_id = connection.connection_id if connection else None
                    raw_status = (connection.status if connection else "not_connected").lower()
                    if connection_id and raw_status not in {"not_connected", "pending", "failed", "expired"}:
                        status = "connected"
                        status_label = "Connected" if raw_status != "error" else "Connected, proxy test recommended"
                        ready = True
                    else:
                        status = raw_status or "not_connected"
                        status_label = "Connect through Nango"
            elif definition["id"] == "twilio_sms":
                if twilio_sms_configured(settings):
                    status = "configured"
                    status_label = "Configured"
                    ready = True
                else:
                    status = "missing_env"
                    status_label = "Add Twilio SMS keys to .env"
                    missing_env = definition["required_env"]
            elif definition["provider"] in {"webhook", "manual_api"}:
                if definition.get("configured"):
                    status = "configured"
                    status_label = "Configured"
                    ready = True
                else:
                    status = "missing_env"
                    status_label = f"Add {', '.join(definition['required_env'])} to .env"
                    missing_env = list(definition["required_env"])
            else:
                status = "configured"
                status_label = "Local feature ready"
                ready = True
        cards.append(
            {
                **definition,
                "enabled": enabled,
                "ready": ready,
                "status": status,
                "status_label": status_label,
                "connection_id": connection_id,
                "missing_env": missing_env,
                "disconnected_at": state.get("disconnected_at"),
            }
        )
    return cards


def _enabled_tool_names(settings, *, client_config: ClientConfig, client_id: str) -> list[str]:
    names: list[str] = []
    for card in _integration_cards(settings, client_config=client_config, client_id=client_id):
        if card["implemented"] and card["enabled"] and card["ready"]:
            names.extend(card.get("allowed_tools") or [])
    return sorted(set(names))


async def _test_webhook_integration(settings, *, integration_id: str, card: dict[str, Any]) -> dict[str, Any]:
    url_by_id = {
        "make": settings.integrations.make_webhook_url,
        "zapier": settings.integrations.zapier_webhook_url,
        "n8n": settings.integrations.n8n_webhook_url,
        "webhook": settings.integrations.generic_webhook_url,
    }
    url = url_by_id.get(integration_id)
    if not url:
        return {
            "ok": False,
            "integration_id": integration_id,
            "status": "missing_env",
            "message": card["status_label"],
            "required_env": card["required_env"],
        }
    started = time.monotonic()
    payload = {
        "event": "verbatim.integration_test",
        "integration_id": integration_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, json=payload)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return {
            "ok": False,
            "integration_id": integration_id,
            "status": "webhook_failed",
            "message": f"{card['label']} webhook test failed: {exc.__class__.__name__}",
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
        }
    return {
        "ok": True,
        "integration_id": integration_id,
        "status": "configured",
        "message": f"{card['label']} webhook accepted the test event.",
        "duration_ms": round((time.monotonic() - started) * 1000, 1),
    }


async def _refresh_nango_connections(settings, *, client_id: str) -> None:
    if not settings.integrations.nango_secret_key:
        return
    client_config = _client_config(settings)
    integration_state = client_config.integrations.get("integrations") or {}
    store = _integration_store(settings)
    nango = NangoClient(settings)
    for definition in integration_definitions(settings):
        if definition.get("provider") != "nango":
            continue
        state = integration_state.get(definition["id"], {})
        if not state.get("enabled"):
            continue
        integration_key = str(definition["integration_key"])
        try:
            connections = await nango.list_connections(client_id=client_id, integration_key=integration_key)
        except NangoError:
            continue
        for connection in connections:
            if not connection.connection_id:
                continue
            store.upsert_connection(
                client_id=client_id,
                provider="nango",
                integration_key=integration_key,
                connection_id=connection.connection_id,
                status=connection.status or "connected",
                allowed_tools=list(definition.get("allowed_tools") or []),
            )


def _integration_status(settings, *, client_id: str) -> dict[str, Any]:
    client_config = _client_config(settings)
    store = _integration_store(settings)
    connections = store.list_connections(client_id=client_id)
    return {
        "client_id": client_id,
        "cards": _integration_cards(settings, client_config=client_config, client_id=client_id),
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
