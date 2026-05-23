from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import re
import threading
import time
from typing import Any

from verbatim.analytics.latency import summarize_call_events
from verbatim.config import clear_settings_cache, get_settings
from verbatim.daily import DailyRoomManager
from verbatim.events import SCHEMA_VERSION, load_events, new_id, normalize_event_name
from verbatim.livekit import LiveKitRoomManager
from verbatim.pipeline.agent import AgentSession, run_voice_agent
from verbatim.stt_config import settings_with_runtime_overrides


ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = ROOT / "static"
ACTIVE_AGENTS: dict[str, asyncio.Task] = {}
CANCEL_TIMEOUT_SECONDS = 5.0
ACCESS_LOG_FILTER_NAME = "verbatim.analytics_poll_filter"
CLIENT_EVENT_WRITE_LOCK = threading.Lock()
CLIENT_EVENT_PREFIXES = (
    "browser.audio.",
    "livekit.client.",
    "hume.client.",
)
CALL_ID_RE = re.compile(r"\bcall_[A-Za-z0-9]+\b")


class _AnalyticsAccessLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        rendered_args = " ".join(str(arg) for arg in (record.args or ()))
        return "/api/analytics/" not in rendered_args


def _install_access_log_filter() -> None:
    access_logger = logging.getLogger("uvicorn.access")
    if any(getattr(item, "name", "") == ACCESS_LOG_FILTER_NAME for item in access_logger.filters):
        return
    access_logger.addFilter(_AnalyticsAccessLogFilter(ACCESS_LOG_FILTER_NAME))


def create_app():
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse
    from fastapi.staticfiles import StaticFiles

    _install_access_log_filter()
    app = FastAPI(title="Verbatim Voice Pipeline", version="0.1.0")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    @app.get("/api/health")
    async def health():
        _prune_finished_agents()
        settings = get_settings()
        return {
            "ok": True,
            "agent_id": settings.agent.agent_id,
            "client_id": settings.agent.client_id,
            "environment": settings.agent.environment,
            "active_agents": len([task for task in ACTIVE_AGENTS.values() if not task.done()]),
        }

    @app.get("/api/config")
    async def runtime_config():
        settings = get_settings()
        return {
            "stt_provider": settings.providers.stt_provider,
            "deepgram_model": settings.providers.deepgram_model,
            "llm_provider": settings.providers.llm_provider,
            "llm_model": settings.providers.llm_model,
            "transport_provider": settings.providers.transport_provider,
            "daily_geo": settings.providers.daily_geo,
            "daily_force_create_room": settings.providers.daily_force_create_room,
            "daily_region_options": [
                {"id": "auto", "label": "Auto", "daily_geo": None},
                {"id": "eu-central-1", "label": "Frankfurt", "daily_geo": "eu-central-1"},
                {"id": "eu-west-2", "label": "London", "daily_geo": "eu-west-2"},
            ],
            "livekit_audio_in_sample_rate": settings.providers.livekit_audio_in_sample_rate,
            "livekit_audio_out_sample_rate": settings.providers.livekit_audio_out_sample_rate,
            "livekit_audio_out_bitrate": settings.providers.livekit_audio_out_bitrate,
            "livekit_audio_out_10ms_chunks": settings.providers.livekit_audio_out_10ms_chunks,
            "livekit_audio_out_auto_silence": settings.providers.livekit_audio_out_auto_silence,
            "livekit_browser_echo_cancellation": settings.providers.livekit_browser_echo_cancellation,
            "livekit_browser_noise_suppression": settings.providers.livekit_browser_noise_suppression,
            "livekit_browser_auto_gain_control": settings.providers.livekit_browser_auto_gain_control,
            "livekit_browser_audio_sample_rate": settings.providers.livekit_browser_audio_sample_rate,
            "transport_options": [
                {"id": "daily", "label": "Daily", "transport_provider": "daily"},
                {"id": "livekit", "label": "LiveKit", "transport_provider": "livekit"},
                {
                    "id": "hume_evi",
                    "label": "Hume EVI",
                    "transport_provider": "hume_evi",
                },
            ],
            "hume_evi_configured": bool(
                settings.providers.hume_api_key and settings.providers.hume_secret_key
            ),
            "hume_evi_config_id": settings.providers.hume_evi_config_id,
            "hume_evi_config_version": settings.providers.hume_evi_config_version,
            "hume_evi_voice_id": settings.providers.hume_evi_voice_id,
            "hume_evi_verbose_transcription": settings.providers.hume_evi_verbose_transcription,
            "hume_evi_send_system_prompt": settings.providers.hume_evi_send_system_prompt,
            "stt_options": [
                {
                    "id": "deepgram_flux",
                    "label": "Flux",
                    "stt_provider": "deepgram_flux",
                    "deepgram_model": "flux-general-en",
                },
                {
                    "id": "nova_3_general",
                    "label": "Nova-3",
                    "stt_provider": "deepgram",
                    "deepgram_model": "nova-3-general",
                },
            ],
            "llm_options": [
                {
                    "id": "gemini_25_flash",
                    "label": "Gemini 2.5 Flash",
                    "llm_provider": "gemini",
                    "llm_model": "gemini-2.5-flash",
                },
                {
                    "id": "groq_llama_31_8b",
                    "label": "Groq LLaMA 3.1 8B",
                    "llm_provider": "groq",
                    "llm_model": "llama-3.1-8b-instant",
                },
                {
                    "id": "openai_4o_mini",
                    "label": "OpenAI GPT-4o mini",
                    "llm_provider": "openai",
                    "llm_model": "gpt-4o-mini",
                },
                {
                    "id": "qwen_35_2b",
                    "label": f"Qwen · {settings.providers.qwen_model}",
                    "llm_provider": "qwen",
                    "llm_model": settings.providers.qwen_model,
                },
                {
                    "id": "xai_grok_41_fast",
                    "label": "xAI Grok 4.1 Fast",
                    "llm_provider": "xai",
                    "llm_model": settings.providers.xai_model,
                },
                {
                    "id": "ultravox_realtime",
                    "label": "UltraVox Realtime",
                    "llm_provider": "ultravox",
                    "llm_model": settings.providers.ultravox_model,
                },
                {
                    "id": "mock_immediate",
                    "label": "Mock immediate",
                    "llm_provider": "mock",
                    "llm_model": "mock-immediate",
                },
            ],
            "tts_text_aggregation_mode": settings.voice.tts_text_aggregation_mode,
            "tts_first_phrase_flush_enabled": settings.voice.tts_first_phrase_flush_enabled,
            "tts_first_flush_timeout_ms": settings.voice.tts_first_flush_timeout_ms,
            "tts_first_flush_min_words": settings.voice.tts_first_flush_min_words,
            "tts_first_flush_max_words": settings.voice.tts_first_flush_max_words,
            "tts_after_first_mode": settings.voice.tts_after_first_mode,
            "cartesia_max_buffer_delay_ms": settings.voice.cartesia_max_buffer_delay_ms,
            "ultravox_turn_endpoint_delay_seconds": (
                settings.providers.ultravox_turn_endpoint_delay_seconds
            ),
            "ultravox_minimum_turn_duration_seconds": (
                settings.providers.ultravox_minimum_turn_duration_seconds
            ),
            "ultravox_minimum_interruption_duration_seconds": (
                settings.providers.ultravox_minimum_interruption_duration_seconds
            ),
            "ultravox_frame_activation_threshold": (
                settings.providers.ultravox_frame_activation_threshold
            ),
            "ultravox_client_buffer_size_ms": settings.providers.ultravox_client_buffer_size_ms,
            "ultravox_media_idle_timeout_seconds": (
                settings.providers.ultravox_media_idle_timeout_seconds
            ),
            "user_turn_stop_timeout": settings.session.user_turn_stop_timeout,
            "llm_history_messages": settings.session.llm_history_messages,
            "llm_max_tokens": settings.prompt.max_tokens,
            "llm_temperature": settings.prompt.temperature,
            "latency_diagnostic_mode": settings.session.latency_diagnostic_mode,
            "final_transcript_eager_commit": settings.session.final_transcript_eager_commit,
            "final_transcript_commit_delay_ms": settings.session.final_transcript_commit_delay_ms,
            "final_transcript_require_complete_utterance": settings.session.final_transcript_require_complete_utterance,
            "final_transcript_fragment_delay_ms": settings.session.final_transcript_fragment_delay_ms,
            "response_style_guard_enabled": settings.session.response_style_guard_enabled,
            "vad_only_user_turn_start": settings.session.vad_only_user_turn_start,
            "mute_user_while_bot_speaking": settings.session.mute_user_while_bot_speaking,
            "llm_prewarm_enabled": settings.session.llm_prewarm_enabled,
            "echo_suppression_ms": settings.session.echo_suppression_ms,
            "fast_ack_enabled": settings.session.fast_ack_enabled,
            "fast_ack_timeout_ms": settings.session.fast_ack_timeout_ms,
            "assistant_min_speak_ms_before_barge_in": (
                settings.session.assistant_min_speak_ms_before_barge_in
            ),
            "barge_in_min_speech_ms": settings.session.barge_in_min_speech_ms,
            "barge_in_min_transcript_words": settings.session.barge_in_min_transcript_words,
            "hard_interrupt_phrases": settings.session.hard_interrupt_phrases,
            "utterance_split_window_ms": settings.session.utterance_split_window_ms,
            "user_resume_after_assistant_window_ms": (
                settings.session.user_resume_after_assistant_window_ms
            ),
        }

    @app.post("/api/rooms")
    async def create_or_reuse_room(payload: dict[str, Any] | None = None):
        _prune_finished_agents()
        stopped_agents = await _cancel_active_agents()
        clear_settings_cache()
        settings = get_settings()
        payload = payload or {}
        try:
            settings = settings_with_runtime_overrides(
                settings,
                transport_provider=payload.get("transport_provider"),
                stt_provider=None,
                deepgram_model=None,
                llm_provider=None,
                llm_model=None,
            )
            daily_geo = (
                _daily_geo_or_none(payload.get("daily_geo"))
                if "daily_geo" in payload
                else settings.providers.daily_geo
            )
            force_create_room = _bool_or_none(payload.get("force_create_room"))
            if daily_geo != settings.providers.daily_geo or force_create_room is not None:
                settings = replace(
                    settings,
                    providers=replace(
                        settings.providers,
                        daily_geo=daily_geo,
                        daily_force_create_room=(
                            force_create_room
                            if force_create_room is not None
                            else settings.providers.daily_force_create_room
                        ),
                    ),
                )
            call_id = new_id("call")
            session_id = new_id("sess")
            room = await _resolve_room(settings, call_id=call_id, session_id=session_id)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "room_url": room.room_url,
            "room_token": room.room_token,
            "room_name": getattr(room, "room_name", None),
            "room_geo": getattr(room, "geo", None),
            "source": room.source,
            "transport_provider": settings.providers.transport_provider,
            "call_id": call_id,
            "session_id": session_id,
            "stopped_agents": stopped_agents,
        }

    @app.post("/api/agent/start")
    async def start_agent(payload: dict[str, Any] | None = None):
        _prune_finished_agents()
        clear_settings_cache()
        settings = get_settings()
        payload = payload or {}
        try:
            settings = settings_with_runtime_overrides(
                settings,
                transport_provider=payload.get("transport_provider"),
                stt_provider=payload.get("stt_provider"),
                deepgram_model=payload.get("deepgram_model"),
                llm_provider=payload.get("llm_provider"),
                llm_model=payload.get("llm_model"),
            )
            daily_geo = (
                _daily_geo_or_none(payload.get("daily_geo"))
                if "daily_geo" in payload
                else settings.providers.daily_geo
            )
            if daily_geo != settings.providers.daily_geo:
                settings = replace(
                    settings,
                    providers=replace(settings.providers, daily_geo=daily_geo),
                )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        call_id = payload.get("call_id") or new_id("call")
        session_id = payload.get("session_id") or new_id("sess")
        try:
            room_url, room_token, room_name = _agent_room_values(settings, payload, call_id=call_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not room_url:
            raise HTTPException(status_code=400, detail="room_url is required.")
        missing = settings.missing_agent_keys()
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required agent environment variables: {', '.join(missing)}",
            )

        existing = ACTIVE_AGENTS.get(call_id)
        if existing and not existing.done():
            return {
                "started": False,
                "already_running": True,
                "call_id": call_id,
                "session_id": session_id,
                "transport_provider": settings.providers.transport_provider,
                "stt_provider": settings.providers.stt_provider,
                "deepgram_model": settings.providers.deepgram_model,
                "llm_provider": settings.providers.llm_provider,
                "llm_model": settings.providers.llm_model,
            }

        stopped_agents = await _cancel_active_agents(except_call_id=call_id)
        task = asyncio.create_task(
            run_voice_agent(
                settings,
                AgentSession(
                    transport_provider=settings.providers.transport_provider,
                    room_url=room_url,
                    room_token=room_token,
                    room_name=room_name,
                    call_id=call_id,
                    session_id=session_id,
                ),
            )
        )
        ACTIVE_AGENTS[call_id] = task
        return {
            "started": True,
            "call_id": call_id,
            "session_id": session_id,
            "transport_provider": settings.providers.transport_provider,
            "room_name": room_name,
            "stt_provider": settings.providers.stt_provider,
            "deepgram_model": settings.providers.deepgram_model,
            "llm_provider": settings.providers.llm_provider,
            "llm_model": settings.providers.llm_model,
            "stopped_agents": stopped_agents,
        }

    @app.post("/api/hume/evi/session")
    async def create_hume_evi_session(payload: dict[str, Any] | None = None):
        _prune_finished_agents()
        stopped_agents = await _cancel_active_agents()
        clear_settings_cache()
        settings = get_settings()
        payload = payload or {}
        missing = _missing_hume_evi_keys(settings)
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required Hume EVI environment variables: {', '.join(missing)}",
            )
        call_id = payload.get("call_id") or new_id("call")
        session_id = payload.get("session_id") or new_id("sess")
        try:
            token_payload = await _create_hume_access_token(settings)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Hume token request failed: {exc.__class__.__name__}",
            ) from exc

        session_settings = _hume_evi_session_settings(settings, session_id=session_id)
        config_id = payload.get("config_id") or settings.providers.hume_evi_config_id
        config_version = (
            _int_or_none(payload.get("config_version"))
            if payload.get("config_version") is not None
            else settings.providers.hume_evi_config_version
        )
        metadata = {
            "transport_provider": "hume_evi",
            "room_name": "hume-evi-direct",
            "stt_provider": "hume_evi",
            "deepgram_model": "hume-evi-direct",
            "llm_provider": "hume_evi",
            "llm_model": "hume-evi",
            "tts_provider": "hume_evi",
            "tts_model": "hume-evi",
            "hume_evi_config_id": config_id,
            "hume_evi_config_version": config_version,
            "hume_evi_voice_id": settings.providers.hume_evi_voice_id,
            "hume_evi_verbose_transcription": settings.providers.hume_evi_verbose_transcription,
            "hume_evi_send_system_prompt": settings.providers.hume_evi_send_system_prompt,
            "stopped_agents": stopped_agents,
        }
        _append_server_event(
            settings,
            call_id=call_id,
            session_id=session_id,
            event_name="session.created",
            provider="hume_evi",
            metadata={"transport_provider": "hume_evi"},
        )
        _append_server_event(
            settings,
            call_id=call_id,
            session_id=session_id,
            event_name="session.configured",
            provider="hume_evi",
            metadata=metadata,
        )
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
            "session_settings": session_settings,
            "stopped_agents": stopped_agents,
        }

    @app.post("/api/agent/stop")
    async def stop_agent(payload: dict[str, Any] | None = None):
        payload = payload or {}
        call_id = payload.get("call_id")
        targets = _agent_targets(call_id)
        fallback_to_all = False
        if call_id and not targets and _active_agent_count() > 0:
            fallback_to_all = True
            targets = _agent_targets(None)
        if not targets:
            return {
                "stopped": False,
                "reason": "no_active_agent",
                "call_id": call_id,
                "active_agents": _active_agent_count(),
                "results": [],
            }

        results = []
        for target_call_id, task in targets:
            result = await _cancel_agent_task(target_call_id, task)
            results.append(result)

        _prune_finished_agents()
        return {
            "stopped": any(
                result["state"] in {"cancelled", "already_done", "completed", "cancelling"}
                for result in results
            ),
            "call_id": call_id,
            "stopped_by": "all_active_agents" if fallback_to_all else "requested_call",
            "active_agents": _active_agent_count(),
            "results": results,
        }

    @app.get("/api/agent/status")
    async def agent_status():
        _prune_finished_agents()
        return {
            call_id: {"done": task.done(), "cancelled": task.cancelled()}
            for call_id, task in ACTIVE_AGENTS.items()
        }

    @app.get("/api/analytics/summary")
    async def analytics_summary(call_id: str | None = None):
        _prune_finished_agents()
        settings = get_settings()
        events = load_events(settings.instrumentation.event_log_path)
        selected_call_id = call_id or _latest_call_id(events)
        summary = summarize_call_events(events, call_id=selected_call_id)
        selected_events = [
            event for event in events if selected_call_id is None or _event_matches_call(event, selected_call_id)
        ]
        summary["active_agents"] = len([task for task in ACTIVE_AGENTS.values() if not task.done()])
        summary["latest_call_id"] = selected_call_id
        summary["event_count"] = len(selected_events)
        summary["latest_events"] = selected_events[-80:]
        summary["provider_metrics"] = _provider_metrics(selected_events)
        summary["livekit_client_stats"] = _latest_livekit_client_stats(selected_events)
        summary["livekit_client_event_counts"] = _client_event_counts(selected_events)
        stt_config = _call_stt_config(selected_events, settings)
        summary["stt_provider"] = stt_config["stt_provider"]
        summary["stt_model"] = stt_config["deepgram_model"]
        summary["llm_provider"] = stt_config["llm_provider"]
        summary["llm_model"] = stt_config["llm_model"]
        summary["tts_provider"] = stt_config["tts_provider"]
        summary["tts_model"] = stt_config["tts_model"]
        summary["transport_provider"] = stt_config["transport_provider"]
        summary["room_name"] = stt_config["room_name"]
        summary["hume_evi_config_id"] = stt_config["hume_evi_config_id"]
        summary["hume_evi_config_version"] = stt_config["hume_evi_config_version"]
        summary["hume_evi_voice_id"] = stt_config["hume_evi_voice_id"]
        summary["hume_evi_verbose_transcription"] = stt_config["hume_evi_verbose_transcription"]
        summary["hume_evi_send_system_prompt"] = stt_config["hume_evi_send_system_prompt"]
        summary["config_snapshot"] = stt_config
        summary["tts_text_aggregation_mode"] = stt_config["tts_text_aggregation_mode"]
        summary["tts_first_phrase_flush_enabled"] = stt_config["tts_first_phrase_flush_enabled"]
        summary["tts_first_flush_timeout_ms"] = stt_config["tts_first_flush_timeout_ms"]
        summary["tts_first_flush_min_words"] = stt_config["tts_first_flush_min_words"]
        summary["tts_first_flush_max_words"] = stt_config["tts_first_flush_max_words"]
        summary["tts_after_first_mode"] = stt_config["tts_after_first_mode"]
        summary["cartesia_max_buffer_delay_ms"] = stt_config["cartesia_max_buffer_delay_ms"]
        summary["user_turn_stop_timeout"] = stt_config["user_turn_stop_timeout"]
        summary["llm_history_messages"] = stt_config["llm_history_messages"]
        summary["llm_max_tokens"] = stt_config["llm_max_tokens"]
        summary["llm_temperature"] = stt_config["llm_temperature"]
        summary["latency_diagnostic_mode"] = stt_config["latency_diagnostic_mode"]
        summary["final_transcript_eager_commit"] = stt_config["final_transcript_eager_commit"]
        summary["vad_only_user_turn_start"] = stt_config["vad_only_user_turn_start"]
        summary["mute_user_while_bot_speaking"] = stt_config["mute_user_while_bot_speaking"]
        summary["llm_prewarm_enabled"] = stt_config["llm_prewarm_enabled"]
        summary["echo_suppression_ms"] = stt_config["echo_suppression_ms"]
        summary["fast_ack_enabled"] = stt_config["fast_ack_enabled"]
        summary["fast_ack_timeout_ms"] = stt_config["fast_ack_timeout_ms"]
        summary["assistant_min_speak_ms_before_barge_in"] = stt_config[
            "assistant_min_speak_ms_before_barge_in"
        ]
        summary["barge_in_min_speech_ms"] = stt_config["barge_in_min_speech_ms"]
        summary["barge_in_min_transcript_words"] = stt_config["barge_in_min_transcript_words"]
        summary["hard_interrupt_phrases"] = stt_config["hard_interrupt_phrases"]
        summary["utterance_split_window_ms"] = stt_config["utterance_split_window_ms"]
        summary["user_resume_after_assistant_window_ms"] = stt_config[
            "user_resume_after_assistant_window_ms"
        ]
        return summary

    @app.post("/api/analytics/client-event")
    async def analytics_client_event(payload: dict[str, Any]):
        settings = get_settings()
        call_id = str(payload.get("call_id") or "").strip()
        if not call_id:
            raise HTTPException(status_code=400, detail="call_id is required")
        event_name = normalize_event_name(str(payload.get("event_name") or "client.event"))
        if not event_name.startswith(CLIENT_EVENT_PREFIXES):
            raise HTTPException(status_code=400, detail="Unsupported client event name")
        metadata = _safe_client_metadata(payload.get("metadata") or {})
        resolved_call_id = _call_id_from_client_metadata(metadata) or call_id
        if resolved_call_id != call_id:
            metadata["reported_call_id"] = call_id
            metadata["resolved_call_id"] = resolved_call_id
            metadata["resolved_call_id_source"] = "client_metadata"
        metadata["source"] = "browser"
        _append_client_event(
            settings,
            call_id=resolved_call_id,
            session_id=str(payload.get("session_id") or ""),
            event_name=event_name,
            provider=str(payload.get("provider") or "browser"),
            metadata=metadata,
        )
        return {"ok": True}

    @app.get("/api/analytics/transcript")
    async def analytics_transcript(call_id: str | None = None):
        settings = get_settings()
        events = load_events(settings.instrumentation.event_log_path)
        selected_call_id = call_id or _latest_call_id(events)
        transcript_items = []
        if selected_call_id:
            transcript_path = settings.instrumentation.transcript_dir / f"{selected_call_id}.jsonl"
            transcript_items = load_events(transcript_path)
        selected_events = [
            event for event in events if selected_call_id is None or _event_matches_call(event, selected_call_id)
        ]
        transcript_items.extend(_hume_transcript_items(selected_events))
        stt_events = [
            event
            for event in selected_events
            if _is_stt_diagnostic_event(event)
        ]
        return {
            "call_id": selected_call_id,
            **_call_stt_config(selected_events, settings),
            "items": transcript_items[-80:],
            "stt_events": stt_events[-80:],
        }

    return app


app = create_app()


def _active_agent_count() -> int:
    return len([task for task in ACTIVE_AGENTS.values() if not task.done()])


def _append_client_event(
    settings,
    *,
    call_id: str,
    session_id: str,
    event_name: str,
    provider: str,
    metadata: dict[str, Any],
) -> None:
    if not settings.instrumentation.enable_jsonl_events:
        return
    event = {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id or "browser",
        "call_id": call_id,
        "turn_id": None,
        "agent_id": settings.agent.agent_id,
        "client_id": settings.agent.client_id,
        "event_name": event_name,
        "timestamp_wall_iso": datetime.now(UTC).isoformat(),
        "timestamp_monotonic_ms": round(time.monotonic() * 1000, 3),
        "provider": provider,
        "metadata": metadata,
    }
    path = settings.instrumentation.event_log_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with CLIENT_EVENT_WRITE_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True, default=str) + "\n")


def _append_server_event(
    settings,
    *,
    call_id: str,
    session_id: str,
    event_name: str,
    provider: str,
    metadata: dict[str, Any],
) -> None:
    if not settings.instrumentation.enable_jsonl_events:
        return
    event = {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "call_id": call_id,
        "turn_id": None,
        "agent_id": settings.agent.agent_id,
        "client_id": settings.agent.client_id,
        "event_name": normalize_event_name(event_name),
        "timestamp_wall_iso": datetime.now(UTC).isoformat(),
        "timestamp_monotonic_ms": round(time.monotonic() * 1000, 3),
        "provider": provider,
        "metadata": metadata,
    }
    path = settings.instrumentation.event_log_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with CLIENT_EVENT_WRITE_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True, default=str) + "\n")


def _missing_hume_evi_keys(settings) -> list[str]:
    missing = []
    if not settings.providers.hume_api_key:
        missing.append("HUME_API_KEY")
    if not settings.providers.hume_secret_key:
        missing.append("HUME_SECRET_KEY")
    return missing


async def _create_hume_access_token(settings) -> dict[str, Any]:
    import httpx

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
        raise RuntimeError("Hume token response did not include an access token")
    return payload


def _hume_evi_session_settings(settings, *, session_id: str) -> dict[str, Any]:
    session_settings: dict[str, Any] = {
        "type": "session_settings",
        "custom_session_id": session_id,
        "context": {
            "type": "persistent",
            "text": _hume_evi_role_context(),
        },
    }
    if settings.providers.hume_evi_voice_id:
        session_settings["voice_id"] = settings.providers.hume_evi_voice_id
    if settings.providers.hume_evi_send_system_prompt:
        session_settings["system_prompt"] = (
            settings.prompt.hume_evi_system_prompt or _default_hume_evi_prompt()
        )
    return session_settings


def _default_hume_evi_prompt() -> str:
    return (
        "You are the receptionist for a Dubai property company on a live business call. "
        "The caller already knows the company and does not want repeated introductions. "
        "Never say your personal name. Never say the company name. Never reintroduce yourself. "
        "Never explain your role unless the caller explicitly asks what you can help with. "
        "If the caller asks why you repeated yourself, answer only: 'You're right. I'll stop doing that.' "
        "Never say you are an AI, LLM, model, bot, or general assistant. "
        "Do not begin replies with generic affirmations. Start with the useful answer. "
        "Do not use casual filler as a habit. Do not use the word 'like' as filler. "
        "Do not repeat, recap, mirror, validate, complete, or label what the caller just said. "
        "Avoid form phrases: sounds like, you're looking for, that's a great budget, rent or purchase, what's your budget, which area, what property are we looking at. "
        "Do not push through a questionnaire. Stay with the caller's current issue. "
        "Ask one question only when a specific detail is needed now. "
        "Prefer useful short lines: 'One sec.' 'I can check.' 'I'll send it on WhatsApp.' 'Which listing was it?' "
        "If the caller is unsure, offer a light next step instead of interrogating them. "
        "If the caller says stop, wait, chill, or let me finish, pause and answer briefly. "
        "If the caller says goodbye, done, thank you, or end the call, close once and stop asking questions. "
        "Good closings: 'I'll WhatsApp you.' 'Speak soon.' 'Take care.' "
        "Avoid market hype, obvious Dubai facts, luxury filler, and repeated WhatsApp send-offs. "
        "Most replies should be 3 to 8 words. Use two short sentences only for direct questions."
    )


def _hume_evi_role_context() -> str:
    return (
        "Call context only, not wording to repeat: this is a Dubai property inquiry. "
        "The caller dislikes repeated identity statements and generic affirmations. "
        "Keep replies short, business-relevant, and focused on the caller's current issue."
    )


def _safe_client_metadata(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return str(value)[:240]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)[:80]
            if key.lower() in {"token", "authorization", "room_token", "jwt", "api_key", "secret"}:
                result[key] = "[redacted]"
            else:
                result[key] = _safe_client_metadata(raw_value, depth=depth + 1)
        return result
    if isinstance(value, list):
        return [_safe_client_metadata(item, depth=depth + 1) for item in value[:24]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        text = str(value) if isinstance(value, str) else value
        if isinstance(text, str):
            return text[:500]
        return text
    return str(value)[:240]


def _call_id_from_client_metadata(value: Any, *, depth: int = 0) -> str | None:
    if depth > 6:
        return None
    if isinstance(value, dict):
        for key in ("identity", "participant", "remote_participants", "audio_elements"):
            if key in value:
                match = _call_id_from_client_metadata(value[key], depth=depth + 1)
                if match:
                    return match
        for nested in value.values():
            match = _call_id_from_client_metadata(nested, depth=depth + 1)
            if match:
                return match
        return None
    if isinstance(value, list):
        for item in value:
            match = _call_id_from_client_metadata(item, depth=depth + 1)
            if match:
                return match
        return None
    if isinstance(value, str):
        match = CALL_ID_RE.search(value)
        return match.group(0) if match else None
    return None


def _is_client_event(event: dict[str, Any]) -> bool:
    event_name = str(event.get("event_name") or "")
    return event_name.startswith(CLIENT_EVENT_PREFIXES) or event.get("provider") == "browser"


def _event_matches_call(event: dict[str, Any], call_id: str) -> bool:
    if event.get("call_id") == call_id:
        return True
    if not _is_client_event(event):
        return False
    metadata = event.get("metadata") or {}
    return _call_id_from_client_metadata(metadata) == call_id


def _latest_livekit_client_stats(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(events):
        if event.get("event_name") == "livekit.client.stats":
            return dict(event.get("metadata") or {})
    return None


def _client_event_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        event_name = str(event.get("event_name") or "")
        if not event_name.startswith(CLIENT_EVENT_PREFIXES):
            continue
        counts[event_name] = counts.get(event_name, 0) + 1
    return counts


def _hume_transcript_items(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    last_by_role: dict[str, tuple[str, float]] = {}
    for event in events:
        event_name = str(event.get("event_name") or "")
        if event_name not in {"hume.client.user_message", "hume.client.assistant_message"}:
            continue
        metadata = event.get("metadata") or {}
        text = metadata.get("transcript") or metadata.get("text_preview") or metadata.get("text")
        if not text:
            continue
        role = "assistant" if event_name.endswith("assistant_message") else "user"
        timestamp = _float_or_none(event.get("timestamp_monotonic_ms"))
        normalized = " ".join(str(text).split())
        previous = last_by_role.get(role)
        if (
            previous
            and previous[0] == normalized
            and timestamp is not None
            and timestamp - previous[1] <= 1800
        ):
            continue
        if timestamp is not None:
            last_by_role[role] = (normalized, timestamp)
        items.append(
            {
                "role": role,
                "text": str(text),
                "turn_id": event.get("turn_id"),
                "timestamp_wall_iso": event.get("timestamp_wall_iso"),
                "metadata": {
                    "frame_type": "HumeEVI",
                    "source": "hume_evi_direct",
                },
            }
        )
    return items


def _prune_finished_agents() -> None:
    for call_id, task in list(ACTIVE_AGENTS.items()):
        if task.done():
            ACTIVE_AGENTS.pop(call_id, None)


def _agent_targets(call_id: Any | None) -> list[tuple[str, asyncio.Task]]:
    _prune_finished_agents()
    if call_id:
        task = ACTIVE_AGENTS.get(str(call_id))
        return [(str(call_id), task)] if task and not task.done() else []
    return [(target_call_id, task) for target_call_id, task in ACTIVE_AGENTS.items() if not task.done()]


async def _cancel_active_agents(*, except_call_id: str | None = None) -> list[dict[str, Any]]:
    targets = [
        (call_id, task)
        for call_id, task in _agent_targets(None)
        if except_call_id is None or call_id != except_call_id
    ]
    results = []
    for call_id, task in targets:
        results.append(await _cancel_agent_task(call_id, task))
    _prune_finished_agents()
    return results


async def _cancel_agent_task(call_id: str, task: asyncio.Task) -> dict[str, Any]:
    if task.done():
        return {"call_id": call_id, "state": "already_done"}

    task.cancel()
    done, pending = await asyncio.wait({task}, timeout=CANCEL_TIMEOUT_SECONDS)
    if pending:
        return {"call_id": call_id, "state": "cancelling"}

    try:
        task.result()
    except asyncio.CancelledError:
        return {"call_id": call_id, "state": "cancelled"}
    except Exception as exc:
        return {
            "call_id": call_id,
            "state": "failed",
            "error_type": exc.__class__.__name__,
            "error_message": str(exc),
        }
    if done:
        ACTIVE_AGENTS.pop(call_id, None)
    return {"call_id": call_id, "state": "completed"}


def _latest_call_id(events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        if _is_client_event(event):
            continue
        call_id = event.get("call_id")
        if call_id:
            return str(call_id)
    for event in reversed(events):
        call_id = event.get("call_id")
        if call_id:
            return str(call_id)
    return None


def _provider_metrics(events: list[dict[str, Any]]) -> dict[str, dict[str, float | None]]:
    metrics: dict[str, dict[str, list[float]]] = {}
    for event in events:
        if event.get("event_name") != "metrics.observed":
            continue
        provider = str(event.get("provider") or "unknown")
        metadata = event.get("metadata") or {}
        metric_type = str(metadata.get("metric_type") or "unknown")
        value = _float_or_none(metadata.get("value"))
        if value is None:
            continue
        metrics.setdefault(provider, {}).setdefault(metric_type, []).append(round(value * 1000, 3))

    return {
        provider: {
            metric_type: round(sum(values) / len(values), 3) if values else None
            for metric_type, values in metric_values.items()
        }
        for provider, metric_values in metrics.items()
    }


def _call_stt_config(events: list[dict[str, Any]], settings) -> dict[str, Any]:
    audio_native_default = settings.providers.llm_provider == "ultravox"
    for event in reversed(events):
        if event.get("event_name") != "session.configured":
            continue
        metadata = event.get("metadata") or {}
        return {
            "transport_provider": metadata.get("transport_provider")
            or settings.providers.transport_provider,
            "room_name": metadata.get("room_name") or settings.providers.livekit_room_name,
            "stt_provider": metadata.get("stt_provider") or settings.providers.stt_provider,
            "deepgram_model": metadata.get("deepgram_model") or settings.providers.deepgram_model,
            "llm_provider": metadata.get("llm_provider") or "gemini",
            "llm_model": metadata.get("llm_model")
            or metadata.get("gemini_model")
            or settings.providers.llm_model,
            "tts_provider": metadata.get("tts_provider")
            or ("ultravox" if metadata.get("llm_provider") == "ultravox" else "cartesia"),
            "tts_model": metadata.get("tts_model")
            or metadata.get("cartesia_model")
            or metadata.get("ultravox_model")
            or settings.voice.cartesia_model,
            "hume_evi_config_id": metadata.get("hume_evi_config_id")
            or settings.providers.hume_evi_config_id,
            "hume_evi_config_version": _int_or_none(metadata.get("hume_evi_config_version"))
            if _int_or_none(metadata.get("hume_evi_config_version")) is not None
            else settings.providers.hume_evi_config_version,
            "hume_evi_voice_id": metadata.get("hume_evi_voice_id")
            or settings.providers.hume_evi_voice_id,
            "hume_evi_verbose_transcription": (
                _bool_or_none(metadata.get("hume_evi_verbose_transcription"))
                if _bool_or_none(metadata.get("hume_evi_verbose_transcription")) is not None
                else settings.providers.hume_evi_verbose_transcription
            ),
            "hume_evi_send_system_prompt": (
                _bool_or_none(metadata.get("hume_evi_send_system_prompt"))
                if _bool_or_none(metadata.get("hume_evi_send_system_prompt")) is not None
                else settings.providers.hume_evi_send_system_prompt
            ),
            "ultravox_turn_endpoint_delay_seconds": _float_or_none(
                metadata.get("ultravox_turn_endpoint_delay_seconds")
            )
            if _float_or_none(metadata.get("ultravox_turn_endpoint_delay_seconds")) is not None
            else settings.providers.ultravox_turn_endpoint_delay_seconds,
            "ultravox_minimum_turn_duration_seconds": _float_or_none(
                metadata.get("ultravox_minimum_turn_duration_seconds")
            )
            if _float_or_none(metadata.get("ultravox_minimum_turn_duration_seconds")) is not None
            else settings.providers.ultravox_minimum_turn_duration_seconds,
            "ultravox_minimum_interruption_duration_seconds": _float_or_none(
                metadata.get("ultravox_minimum_interruption_duration_seconds")
            )
            if _float_or_none(
                metadata.get("ultravox_minimum_interruption_duration_seconds")
            )
            is not None
            else settings.providers.ultravox_minimum_interruption_duration_seconds,
            "ultravox_frame_activation_threshold": _float_or_none(
                metadata.get("ultravox_frame_activation_threshold")
            )
            if _float_or_none(metadata.get("ultravox_frame_activation_threshold")) is not None
            else settings.providers.ultravox_frame_activation_threshold,
            "ultravox_client_buffer_size_ms": _int_or_none(
                metadata.get("ultravox_client_buffer_size_ms")
            )
            if _int_or_none(metadata.get("ultravox_client_buffer_size_ms")) is not None
            else settings.providers.ultravox_client_buffer_size_ms,
            "ultravox_media_idle_timeout_seconds": _float_or_none(
                metadata.get("ultravox_media_idle_timeout_seconds")
            )
            if _float_or_none(metadata.get("ultravox_media_idle_timeout_seconds")) is not None
            else settings.providers.ultravox_media_idle_timeout_seconds,
            "livekit_audio_in_sample_rate": _int_or_none(
                metadata.get("livekit_audio_in_sample_rate")
            )
            if _int_or_none(metadata.get("livekit_audio_in_sample_rate")) is not None
            else settings.providers.livekit_audio_in_sample_rate,
            "livekit_audio_out_sample_rate": _int_or_none(
                metadata.get("livekit_audio_out_sample_rate")
            )
            if _int_or_none(metadata.get("livekit_audio_out_sample_rate")) is not None
            else settings.providers.livekit_audio_out_sample_rate,
            "livekit_audio_out_bitrate": _int_or_none(metadata.get("livekit_audio_out_bitrate"))
            or settings.providers.livekit_audio_out_bitrate,
            "livekit_audio_out_10ms_chunks": _int_or_none(
                metadata.get("livekit_audio_out_10ms_chunks")
            )
            or settings.providers.livekit_audio_out_10ms_chunks,
            "livekit_audio_out_auto_silence": (
                _bool_or_none(metadata.get("livekit_audio_out_auto_silence"))
                if _bool_or_none(metadata.get("livekit_audio_out_auto_silence")) is not None
                else settings.providers.livekit_audio_out_auto_silence
            ),
            "livekit_browser_echo_cancellation": (
                _bool_or_none(metadata.get("livekit_browser_echo_cancellation"))
                if _bool_or_none(metadata.get("livekit_browser_echo_cancellation")) is not None
                else settings.providers.livekit_browser_echo_cancellation
            ),
            "livekit_browser_noise_suppression": (
                _bool_or_none(metadata.get("livekit_browser_noise_suppression"))
                if _bool_or_none(metadata.get("livekit_browser_noise_suppression")) is not None
                else settings.providers.livekit_browser_noise_suppression
            ),
            "livekit_browser_auto_gain_control": (
                _bool_or_none(metadata.get("livekit_browser_auto_gain_control"))
                if _bool_or_none(metadata.get("livekit_browser_auto_gain_control")) is not None
                else settings.providers.livekit_browser_auto_gain_control
            ),
            "livekit_browser_audio_sample_rate": _int_or_none(
                metadata.get("livekit_browser_audio_sample_rate")
            )
            if _int_or_none(metadata.get("livekit_browser_audio_sample_rate")) is not None
            else settings.providers.livekit_browser_audio_sample_rate,
            "eager_eot_enabled": (
                _bool_or_none(metadata.get("eager_eot_enabled"))
                if _bool_or_none(metadata.get("eager_eot_enabled")) is not None
                else settings.providers.stt_provider == "deepgram_flux"
                and settings.providers.deepgram_flux_eager_eot_threshold is not None
            ),
            "deepgram_endpointing": _int_or_none(metadata.get("deepgram_endpointing"))
            or settings.providers.deepgram_endpointing,
            "deepgram_utterance_end_ms": _int_or_none(metadata.get("deepgram_utterance_end_ms"))
            or settings.providers.deepgram_utterance_end_ms,
            "deepgram_flux_eager_eot_threshold": _float_or_none(
                metadata.get("deepgram_flux_eager_eot_threshold")
            )
            or settings.providers.deepgram_flux_eager_eot_threshold,
            "deepgram_flux_eot_threshold": _float_or_none(
                metadata.get("deepgram_flux_eot_threshold")
            )
            or settings.providers.deepgram_flux_eot_threshold,
            "deepgram_flux_eot_timeout_ms": _int_or_none(metadata.get("deepgram_flux_eot_timeout_ms"))
            or settings.providers.deepgram_flux_eot_timeout_ms,
            "tts_text_aggregation_mode": metadata.get("tts_text_aggregation_mode")
            or settings.voice.tts_text_aggregation_mode,
            "tts_first_phrase_flush_enabled": (
                _bool_or_none(metadata.get("tts_first_phrase_flush_enabled"))
                if _bool_or_none(metadata.get("tts_first_phrase_flush_enabled")) is not None
                else settings.voice.tts_first_phrase_flush_enabled
            ),
            "tts_first_flush_timeout_ms": _int_or_none(
                metadata.get("tts_first_flush_timeout_ms")
            )
            or settings.voice.tts_first_flush_timeout_ms,
            "tts_first_flush_min_words": _int_or_none(
                metadata.get("tts_first_flush_min_words")
            )
            or settings.voice.tts_first_flush_min_words,
            "tts_first_flush_max_words": _int_or_none(
                metadata.get("tts_first_flush_max_words")
            )
            or settings.voice.tts_first_flush_max_words,
            "tts_after_first_mode": metadata.get("tts_after_first_mode")
            or settings.voice.tts_after_first_mode,
            "cartesia_max_buffer_delay_ms": _int_or_none(
                metadata.get("cartesia_max_buffer_delay_ms")
            )
            if _int_or_none(metadata.get("cartesia_max_buffer_delay_ms")) is not None
            else settings.voice.cartesia_max_buffer_delay_ms,
            "user_turn_stop_timeout": _float_or_none(metadata.get("user_turn_stop_timeout"))
            or settings.session.user_turn_stop_timeout,
            "llm_history_messages": _int_or_none(metadata.get("llm_history_messages"))
            or settings.session.llm_history_messages,
            "llm_max_tokens": _int_or_none(metadata.get("llm_max_tokens"))
            or settings.prompt.max_tokens,
            "llm_temperature": _float_or_none(metadata.get("llm_temperature"))
            if _float_or_none(metadata.get("llm_temperature")) is not None
            else settings.prompt.temperature,
            "latency_diagnostic_mode": (
                _bool_or_none(metadata.get("latency_diagnostic_mode"))
                if _bool_or_none(metadata.get("latency_diagnostic_mode")) is not None
                else settings.session.latency_diagnostic_mode
            ),
            "final_transcript_eager_commit": (
                _bool_or_none(metadata.get("final_transcript_eager_commit"))
                if _bool_or_none(metadata.get("final_transcript_eager_commit")) is not None
                else settings.session.final_transcript_eager_commit
            ),
            "vad_only_user_turn_start": (
                _bool_or_none(metadata.get("vad_only_user_turn_start"))
                if _bool_or_none(metadata.get("vad_only_user_turn_start")) is not None
                else settings.session.vad_only_user_turn_start
            ),
            "mute_user_while_bot_speaking": (
                _bool_or_none(metadata.get("mute_user_while_bot_speaking"))
                if _bool_or_none(metadata.get("mute_user_while_bot_speaking")) is not None
                else settings.session.mute_user_while_bot_speaking
            ),
            "llm_prewarm_enabled": (
                _bool_or_none(metadata.get("llm_prewarm_enabled"))
                if _bool_or_none(metadata.get("llm_prewarm_enabled")) is not None
                else settings.session.llm_prewarm_enabled
            ),
            "echo_suppression_ms": _int_or_none(metadata.get("echo_suppression_ms"))
            or settings.session.echo_suppression_ms,
            "fast_ack_enabled": (
                _bool_or_none(metadata.get("fast_ack_enabled"))
                if _bool_or_none(metadata.get("fast_ack_enabled")) is not None
                else settings.session.fast_ack_enabled
            ),
            "fast_ack_timeout_ms": _int_or_none(metadata.get("fast_ack_timeout_ms"))
            or settings.session.fast_ack_timeout_ms,
            "assistant_min_speak_ms_before_barge_in": _int_or_none(
                metadata.get("assistant_min_speak_ms_before_barge_in")
            )
            or settings.session.assistant_min_speak_ms_before_barge_in,
            "barge_in_min_speech_ms": _int_or_none(metadata.get("barge_in_min_speech_ms"))
            or settings.session.barge_in_min_speech_ms,
            "barge_in_min_transcript_words": _int_or_none(
                metadata.get("barge_in_min_transcript_words")
            )
            or settings.session.barge_in_min_transcript_words,
            "hard_interrupt_phrases": metadata.get("hard_interrupt_phrases")
            or settings.session.hard_interrupt_phrases,
            "utterance_split_window_ms": _int_or_none(
                metadata.get("utterance_split_window_ms")
            )
            or settings.session.utterance_split_window_ms,
            "user_resume_after_assistant_window_ms": _int_or_none(
                metadata.get("user_resume_after_assistant_window_ms")
            )
            or settings.session.user_resume_after_assistant_window_ms,
        }
    return {
        "transport_provider": settings.providers.transport_provider,
        "room_name": settings.providers.livekit_room_name,
        "daily_geo": settings.providers.daily_geo,
        "daily_force_create_room": settings.providers.daily_force_create_room,
        "stt_provider": "ultravox" if audio_native_default else settings.providers.stt_provider,
        "deepgram_model": settings.providers.ultravox_model
        if audio_native_default
        else settings.providers.deepgram_model,
        "llm_provider": settings.providers.llm_provider,
        "llm_model": settings.providers.llm_model,
        "tts_provider": "ultravox" if audio_native_default else "cartesia",
        "tts_model": settings.providers.ultravox_model
        if audio_native_default
        else settings.voice.cartesia_model,
        "hume_evi_config_id": settings.providers.hume_evi_config_id,
        "hume_evi_config_version": settings.providers.hume_evi_config_version,
        "hume_evi_voice_id": settings.providers.hume_evi_voice_id,
        "hume_evi_verbose_transcription": settings.providers.hume_evi_verbose_transcription,
        "hume_evi_send_system_prompt": settings.providers.hume_evi_send_system_prompt,
        "ultravox_turn_endpoint_delay_seconds": settings.providers.ultravox_turn_endpoint_delay_seconds,
        "ultravox_minimum_turn_duration_seconds": (
            settings.providers.ultravox_minimum_turn_duration_seconds
        ),
        "ultravox_minimum_interruption_duration_seconds": (
            settings.providers.ultravox_minimum_interruption_duration_seconds
        ),
        "ultravox_frame_activation_threshold": settings.providers.ultravox_frame_activation_threshold,
        "ultravox_client_buffer_size_ms": settings.providers.ultravox_client_buffer_size_ms,
        "ultravox_media_idle_timeout_seconds": settings.providers.ultravox_media_idle_timeout_seconds,
        "livekit_audio_in_sample_rate": settings.providers.livekit_audio_in_sample_rate,
        "livekit_audio_out_sample_rate": settings.providers.livekit_audio_out_sample_rate,
        "livekit_audio_out_bitrate": settings.providers.livekit_audio_out_bitrate,
        "livekit_audio_out_10ms_chunks": settings.providers.livekit_audio_out_10ms_chunks,
        "livekit_audio_out_auto_silence": settings.providers.livekit_audio_out_auto_silence,
        "livekit_browser_echo_cancellation": settings.providers.livekit_browser_echo_cancellation,
        "livekit_browser_noise_suppression": settings.providers.livekit_browser_noise_suppression,
        "livekit_browser_auto_gain_control": settings.providers.livekit_browser_auto_gain_control,
        "livekit_browser_audio_sample_rate": settings.providers.livekit_browser_audio_sample_rate,
        "eager_eot_enabled": not audio_native_default
        and settings.providers.stt_provider == "deepgram_flux"
        and settings.providers.deepgram_flux_eager_eot_threshold is not None,
        "deepgram_endpointing": settings.providers.deepgram_endpointing,
        "deepgram_utterance_end_ms": settings.providers.deepgram_utterance_end_ms,
        "deepgram_flux_eager_eot_threshold": settings.providers.deepgram_flux_eager_eot_threshold,
        "deepgram_flux_eot_threshold": settings.providers.deepgram_flux_eot_threshold,
        "deepgram_flux_eot_timeout_ms": settings.providers.deepgram_flux_eot_timeout_ms,
        "tts_text_aggregation_mode": settings.voice.tts_text_aggregation_mode,
        "tts_first_phrase_flush_enabled": settings.voice.tts_first_phrase_flush_enabled,
        "tts_first_flush_timeout_ms": settings.voice.tts_first_flush_timeout_ms,
        "tts_first_flush_min_words": settings.voice.tts_first_flush_min_words,
        "tts_first_flush_max_words": settings.voice.tts_first_flush_max_words,
        "tts_after_first_mode": settings.voice.tts_after_first_mode,
        "cartesia_max_buffer_delay_ms": settings.voice.cartesia_max_buffer_delay_ms,
        "user_turn_stop_timeout": settings.session.user_turn_stop_timeout,
        "llm_history_messages": settings.session.llm_history_messages,
        "llm_max_tokens": settings.prompt.max_tokens,
        "llm_temperature": settings.prompt.temperature,
        "latency_diagnostic_mode": settings.session.latency_diagnostic_mode,
        "final_transcript_eager_commit": settings.session.final_transcript_eager_commit,
        "vad_only_user_turn_start": settings.session.vad_only_user_turn_start,
        "mute_user_while_bot_speaking": settings.session.mute_user_while_bot_speaking,
        "llm_prewarm_enabled": settings.session.llm_prewarm_enabled,
        "echo_suppression_ms": settings.session.echo_suppression_ms,
        "fast_ack_enabled": settings.session.fast_ack_enabled,
        "fast_ack_timeout_ms": settings.session.fast_ack_timeout_ms,
        "assistant_min_speak_ms_before_barge_in": (
            settings.session.assistant_min_speak_ms_before_barge_in
        ),
        "barge_in_min_speech_ms": settings.session.barge_in_min_speech_ms,
        "barge_in_min_transcript_words": settings.session.barge_in_min_transcript_words,
        "hard_interrupt_phrases": settings.session.hard_interrupt_phrases,
        "utterance_split_window_ms": settings.session.utterance_split_window_ms,
        "user_resume_after_assistant_window_ms": (
            settings.session.user_resume_after_assistant_window_ms
        ),
    }


async def _resolve_room(settings, *, call_id: str, session_id: str):
    if settings.providers.transport_provider == "livekit":
        return await LiveKitRoomManager(settings).resolve_room(call_id=call_id, session_id=session_id)
    return await DailyRoomManager(settings).resolve_room()


def _agent_room_values(
    settings,
    payload: dict[str, Any],
    *,
    call_id: str,
) -> tuple[str | None, str | None, str | None]:
    if settings.providers.transport_provider == "livekit":
        room_url = payload.get("room_url") or settings.providers.livekit_url
        room_name = payload.get("room_name") or settings.providers.livekit_room_name
        if not room_name:
            raise ValueError("room_name is required for LiveKit. Click Create Room first.")
        bot_token = LiveKitRoomManager(settings).bot_token(room_name=room_name, call_id=call_id)
        return room_url, bot_token, room_name

    room_url = payload.get("room_url") or settings.providers.daily_room_url
    room_token = payload.get("room_token") or settings.providers.daily_room_token
    return room_url, room_token, None


def _is_stt_diagnostic_event(event: dict[str, Any]) -> bool:
    event_name = str(event.get("event_name", ""))
    provider = event.get("provider")
    if event_name.startswith("hume.client.") and event_name.endswith("_message"):
        return True
    if event_name.startswith(("stt.", "user.speech", "vad.")):
        return True
    return event_name.endswith((".error", ".timeout")) and provider in {"deepgram", "deepgram_flux"}


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return None


def _daily_geo_or_none(value: Any) -> str | None:
    if value is None:
        return None
    geo = str(value).strip()
    if not geo or geo.lower() in {"auto", "default", "none", "null"}:
        return None
    allowed = {
        "af-south-1",
        "ap-northeast-2",
        "ap-south-1",
        "ap-southeast-1",
        "ap-southeast-2",
        "eu-central-1",
        "eu-west-2",
        "sa-east-1",
        "us-east-1",
        "us-west-2",
    }
    if geo not in allowed:
        raise ValueError(f"Unsupported Daily geo region: {geo}")
    return geo


def main() -> None:
    import uvicorn

    uvicorn.run("verbatim.server:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
