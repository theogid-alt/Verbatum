from __future__ import annotations

import asyncio
from dataclasses import dataclass
import datetime
import json
import re
import sys
import traceback
import uuid

from verbatim.config import Settings
from verbatim.events import EventLogger, new_id
from verbatim.instrumentation.recorder import CallRecorder
from verbatim.pipeline.pipecat_processors import (
    create_alicia_conversation_mode_processor,
    create_context_limiter_processor,
    create_final_transcript_eager_llm_processor,
    create_flux_eager_llm_processor,
    create_flux_final_context_gate_processor,
    create_fast_ack_processor,
    create_instrumentation_processor,
    create_llm_error_recovery_processor,
    create_response_style_guard_processor,
    create_user_audio_mute_processor,
)


@dataclass(frozen=True)
class AgentSession:
    room_url: str
    transport_provider: str = "daily"
    room_token: str | None = None
    room_name: str | None = None
    call_id: str | None = None
    session_id: str | None = None


class AgentStartError(RuntimeError):
    pass


async def run_voice_agent(settings: Settings, session: AgentSession) -> None:
    missing = settings.missing_agent_keys()
    if missing:
        raise AgentStartError(f"Missing required agent environment variables: {', '.join(missing)}")

    session_id = session.session_id or new_id("sess")
    call_id = session.call_id or new_id("call")
    logger = EventLogger(
        settings.instrumentation,
        session_id=session_id,
        call_id=call_id,
        agent_id=settings.agent.agent_id,
        client_id=settings.agent.client_id,
    )
    recorder = CallRecorder(logger)
    recorder.set_llm_provider(settings.providers.llm_provider, settings.providers.llm_model)
    recorder.configure_turn_policy(
        assistant_min_speak_ms_before_barge_in=(
            settings.session.assistant_min_speak_ms_before_barge_in
        ),
        barge_in_min_speech_ms=settings.session.barge_in_min_speech_ms,
        barge_in_min_transcript_words=settings.session.barge_in_min_transcript_words,
        mute_user_while_bot_speaking=settings.session.mute_user_while_bot_speaking,
        hard_interrupt_phrases=settings.session.hard_interrupt_phrases,
        utterance_split_window_ms=settings.session.utterance_split_window_ms,
        user_resume_after_assistant_window_ms=(
            settings.session.user_resume_after_assistant_window_ms
        ),
    )
    audio_native = settings.providers.llm_provider == "ultravox"
    recorder.start_session()
    recorder.emit(
        "session.configured",
        provider="pipeline",
        metadata={
            "stt_provider": "ultravox" if audio_native else settings.providers.stt_provider,
            "deepgram_model": settings.providers.ultravox_model
            if audio_native
            else settings.providers.deepgram_model,
            "llm_provider": settings.providers.llm_provider,
            "llm_model": settings.providers.llm_model,
            "gemini_model": settings.providers.gemini_model,
            "openai_model": settings.providers.openai_model,
            "groq_model": settings.providers.groq_model,
            "qwen_model": settings.providers.qwen_model,
            "xai_model": settings.providers.xai_model,
            "ultravox_model": settings.providers.ultravox_model,
            "ultravox_voice_id": settings.providers.ultravox_voice_id,
            "ultravox_max_duration_seconds": settings.providers.ultravox_max_duration_seconds,
            "ultravox_turn_endpoint_delay_seconds": settings.providers.ultravox_turn_endpoint_delay_seconds,
            "ultravox_minimum_turn_duration_seconds": settings.providers.ultravox_minimum_turn_duration_seconds,
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
            "tts_provider": "ultravox" if audio_native else "cartesia",
            "cartesia_model": settings.providers.ultravox_model
            if audio_native
            else settings.voice.cartesia_model,
            "eager_eot_enabled": False
            if audio_native
            else settings.providers.stt_provider == "deepgram_flux"
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
            "transport_provider": session.transport_provider,
            "room_name": session.room_name,
        },
    )

    try:
        _setup_provider_log_redaction()
        _setup_otel_if_enabled(settings)

        from pipecat.audio.vad.silero import SileroVADAnalyzer
        from pipecat.pipeline.pipeline import Pipeline
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineParams, PipelineTask
        from pipecat.processors.aggregators.llm_context import LLMContext
        from pipecat.processors.aggregators.llm_response_universal import (
            LLMContextAggregatorPair,
            LLMUserAggregatorParams,
        )
        from pipecat.services.cartesia.tts import CartesiaTTSService
        from pipecat.services.tts_service import TextAggregationMode

        if audio_native:
            await _run_ultravox_realtime_pipeline(
                settings,
                session,
                recorder,
                Pipeline,
                PipelineRunner,
                PipelineParams,
                PipelineTask,
            )
            recorder.end_session(_session_outcome(recorder))
            logger.flush()
            return

        vad_analyzer = SileroVADAnalyzer()
        transport = _build_transport(settings, session)

        stt = _build_stt(settings)
        llm = _build_llm(settings, recorder)

        tts = _build_tts(settings, recorder, CartesiaTTSService, TextAggregationMode)

        context = LLMContext()
        user_turn_strategies = _build_user_turn_strategies(settings)
        user_mute_strategies = _build_user_mute_strategies(settings)
        user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
            context,
            user_params=LLMUserAggregatorParams(
                user_turn_strategies=user_turn_strategies,
                user_mute_strategies=user_mute_strategies,
                vad_analyzer=vad_analyzer,
                user_turn_stop_timeout=settings.session.user_turn_stop_timeout,
            ),
        )

        _register_transport_handlers(transport, recorder, provider=session.transport_provider)
        task_ref: dict[str, object] = {}
        _register_stt_handlers(stt, recorder, task_ref)
        _register_transcript_handlers(user_aggregator, assistant_aggregator, recorder)
        _register_tts_handlers(tts, recorder)

        pipeline = Pipeline(
            [
                transport.input(),
                create_instrumentation_processor(
                    "verbatim-input-events",
                    recorder,
                    task_ref=task_ref,
                    echo_suppression_ms=settings.session.echo_suppression_ms,
                ),
                stt,
                create_instrumentation_processor(
                    "verbatim-stt-events",
                    recorder,
                    task_ref=task_ref,
                    echo_suppression_ms=settings.session.echo_suppression_ms,
                ),
                create_flux_eager_llm_processor(
                    "verbatim-flux-eager-llm",
                    context=context,
                    recorder=recorder,
                    enabled=settings.providers.stt_provider == "deepgram_flux",
                ),
                create_final_transcript_eager_llm_processor(
                    "verbatim-final-transcript-eager-llm",
                    context=context,
                    recorder=recorder,
                    enabled=settings.session.latency_diagnostic_mode
                    and settings.session.final_transcript_eager_commit
                    and settings.providers.stt_provider == "deepgram",
                    commit_delay_ms=settings.session.final_transcript_commit_delay_ms,
                    require_complete_utterance=settings.session.final_transcript_require_complete_utterance,
                    fragment_delay_ms=settings.session.final_transcript_fragment_delay_ms,
                ),
                user_aggregator,
                create_flux_final_context_gate_processor(
                    "verbatim-flux-final-context-gate",
                    recorder=recorder,
                    enabled=settings.session.latency_diagnostic_mode
                    or settings.providers.stt_provider == "deepgram_flux",
                ),
                create_instrumentation_processor(
                    "verbatim-llm-queue-events", recorder, task_ref=task_ref
                ),
                create_context_limiter_processor(
                    "verbatim-context-limiter",
                    max_messages=settings.session.llm_history_messages,
                    recorder=recorder,
                ),
                create_alicia_conversation_mode_processor(
                    "verbatim-alicia-mode",
                    recorder=recorder,
                    enabled=settings.providers.llm_provider != "mock",
                ),
                create_instrumentation_processor(
                    "verbatim-pre-llm-events", recorder, task_ref=task_ref
                ),
                llm,
                create_llm_error_recovery_processor(
                    "verbatim-llm-error-recovery",
                    recorder=recorder,
                ),
                create_instrumentation_processor("verbatim-llm-events", recorder, task_ref=task_ref),
                create_response_style_guard_processor(
                    "verbatim-response-style-guard",
                    recorder=recorder,
                    enabled=settings.session.response_style_guard_enabled,
                ),
                create_fast_ack_processor(
                    "verbatim-fast-ack",
                    recorder=recorder,
                    enabled=settings.session.fast_ack_enabled,
                    timeout_ms=settings.session.fast_ack_timeout_ms,
                    text=settings.session.fast_ack_text,
                ),
                tts,
                create_instrumentation_processor("verbatim-tts-events", recorder, task_ref=task_ref),
                transport.output(),
                create_instrumentation_processor(
                    "verbatim-output-events", recorder, task_ref=task_ref
                ),
                assistant_aggregator,
            ]
        )

        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                enable_metrics=True,
                enable_usage_metrics=True,
                report_only_initial_ttfb=False,
                audio_in_sample_rate=16000,
                audio_out_sample_rate=24000,
            ),
            idle_timeout_secs=settings.session.idle_timeout_seconds,
        )
        task_ref["task"] = task
        _register_task_handlers(task, recorder, greeting=settings.prompt.greeting)

        await _prewarm_llm_provider(settings, recorder)

        runner = PipelineRunner(handle_sigint=False)
        await runner.run(task)
        recorder.end_session("completed")
        logger.flush()
    except asyncio.CancelledError:
        recorder.emit(
            "session.ended",
            provider="pipeline",
            metadata={"outcome": "cancelled"},
        )
        recorder.write_call_summary(outcome="cancelled")
        logger.flush()
        raise
    except Exception as exc:
        recorder.emit(
            "turn.failed",
            provider="pipeline",
            metadata={"error_type": exc.__class__.__name__, "error_message": str(exc)},
        )
        recorder.emit(
            "session.ended",
            provider="pipeline",
            metadata={
                "outcome": "failed",
                "error_type": exc.__class__.__name__,
                "traceback": traceback.format_exc(limit=8),
            },
        )
        recorder.write_call_summary(outcome="failed")
        logger.flush()
        raise


def _session_outcome(recorder: CallRecorder) -> str:
    return "failed" if any(event.get("event_name") == "turn.failed" for event in recorder.events) else "completed"


async def _run_ultravox_realtime_pipeline(
    settings: Settings,
    session: AgentSession,
    recorder: CallRecorder,
    Pipeline,
    PipelineRunner,
    PipelineParams,
    PipelineTask,
) -> None:
    if (session.transport_provider or settings.providers.transport_provider).lower() != "livekit":
        raise AgentStartError("UltraVox realtime mode currently requires LiveKit transport.")

    transport = _build_transport(settings, session)
    ultravox = _build_ultravox_realtime_service(settings, session, recorder)
    _register_transport_handlers(transport, recorder, provider=session.transport_provider)

    task_ref: dict[str, object] = {}
    input_processors = [
        transport.input(),
        create_instrumentation_processor(
            "verbatim-input-events",
            recorder,
            task_ref=task_ref,
            echo_suppression_ms=settings.session.echo_suppression_ms,
        ),
    ]
    if settings.session.mute_user_while_bot_speaking:
        input_processors.append(
            create_user_audio_mute_processor("verbatim-ultravox-input-mute", recorder)
        )
    pipeline = Pipeline(
        [
            *input_processors,
            ultravox,
            create_instrumentation_processor("verbatim-llm-events", recorder, task_ref=task_ref),
            create_instrumentation_processor("verbatim-tts-events", recorder, task_ref=task_ref),
            transport.output(),
            create_instrumentation_processor("verbatim-output-events", recorder, task_ref=task_ref),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
            report_only_initial_ttfb=False,
            audio_in_sample_rate=16000,
            audio_out_sample_rate=48000,
        ),
        idle_timeout_secs=settings.session.idle_timeout_seconds,
    )
    task_ref["task"] = task
    _register_task_handlers(task, recorder, greeting=None)

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)


def _build_ultravox_realtime_service(
    settings: Settings,
    session: AgentSession,
    recorder: CallRecorder,
):
    from pipecat.services.ultravox.llm import OneShotInputParams, UltravoxRealtimeLLMService

    ultravox_cls = _instrumented_ultravox_realtime_service(UltravoxRealtimeLLMService, recorder)
    voice = None
    if settings.providers.ultravox_voice_id:
        try:
            voice = uuid.UUID(settings.providers.ultravox_voice_id)
        except ValueError as exc:
            raise AgentStartError(
                "VERBATIM_ULTRAVOX_VOICE_ID must be the UltraVox voice UUID "
                "(for example e6fce4ac-da54-43e9-8fb2-66de86f72a5b), not the "
                "underlying provider voice id such as an ElevenLabs RNnk... id."
            ) from exc

    max_duration_seconds = min(
        max(int(settings.providers.ultravox_max_duration_seconds), 10),
        3600,
    )
    extra: dict[str, object] = {}
    extra["joinTimeout"] = "10s"
    vad_settings = _ultravox_vad_settings(settings)
    if vad_settings:
        extra["vadSettings"] = vad_settings
    media_idle_timeout = _duration_seconds(settings.providers.ultravox_media_idle_timeout_seconds)
    if media_idle_timeout:
        extra["mediaIdleTimeout"] = media_idle_timeout
    server_websocket = _ultravox_server_websocket_settings(settings)
    if server_websocket:
        extra["medium"] = {"serverWebSocket": server_websocket}
    if settings.prompt.greeting:
        extra["firstSpeaker"] = "FIRST_SPEAKER_AGENT"
        extra["firstSpeakerSettings"] = {
            "agent": {
                "text": settings.prompt.greeting,
                "delay": "0s",
                "uninterruptible": False,
            }
        }

    return ultravox_cls(
        params=OneShotInputParams(
            api_key=settings.providers.ultravox_api_key or "",
            system_prompt=settings.prompt.system_prompt,
            temperature=settings.prompt.temperature,
            model=settings.providers.ultravox_model,
            voice=voice,
            metadata={
                "call_id": session.call_id or "",
                "session_id": session.session_id or "",
                "agent_id": settings.agent.agent_id,
            },
            output_medium="voice",
            max_duration=datetime.timedelta(seconds=max_duration_seconds),
            extra=extra,
        ),
        settings=UltravoxRealtimeLLMService.Settings(
            model=settings.providers.ultravox_model,
            system_instruction=settings.prompt.system_prompt,
            temperature=settings.prompt.temperature,
            output_medium="voice",
        ),
    )


def _instrumented_ultravox_realtime_service(base_cls, recorder: CallRecorder):
    class InstrumentedUltravoxRealtimeLLMService(base_cls):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if not hasattr(self, "_selected_tools"):
                self._selected_tools = None
            self._verbatim_normal_close_logged = False

        def _is_normal_websocket_close(self, exc: Exception) -> bool:
            text = str(exc)
            return exc.__class__.__name__ == "ConnectionClosedOK" or "received 1000 (OK)" in text

        def _emit_normal_websocket_close(self, exc: Exception) -> None:
            if self._verbatim_normal_close_logged:
                return
            self._verbatim_normal_close_logged = True
            recorder.emit(
                "ultravox.websocket_closed",
                provider="ultravox",
                metadata={
                    "error_type": exc.__class__.__name__,
                    "error_message": _sanitize_provider_error(str(exc)),
                    "fatal": False,
                },
            )

        async def _send(self, content):
            if self._disconnecting or not self._socket:
                return
            try:
                if isinstance(content, bytes):
                    await self._socket.send(content)
                else:
                    await self._socket.send(json.dumps(content))
            except Exception as exc:
                if self._disconnecting or not self._socket:
                    return
                if self._is_normal_websocket_close(exc):
                    self._emit_normal_websocket_close(exc)
                    self._socket = None
                    return
                await self.push_error("Ultravox websocket send error", exc, fatal=True)

        async def _receive_messages(self):
            if not self._socket:
                return
            try:
                async for message in self._socket:
                    try:
                        if isinstance(message, bytes):
                            await self._handle_audio(message)
                            continue

                        data = json.loads(message)
                        message_type = str(data.get("type") or "unknown")
                        if message_type in {
                            "call_started",
                            "call_event",
                            "debug",
                            "playback_clear_buffer",
                            "state",
                            "user_started_speaking",
                            "user_stopped_speaking",
                        }:
                            recorder.emit(
                                f"ultravox.{message_type}",
                                provider="ultravox",
                                metadata=_ultravox_message_metadata(data),
                            )
                        if message_type == "transcript":
                            recorder.emit(
                                f"ultravox.transcript.{str(data.get('role') or 'unknown')}",
                                provider="ultravox",
                                metadata=_ultravox_message_metadata(data),
                            )

                        match message_type:
                            case "state":
                                if self._bot_responding and data.get("state") != "speaking":
                                    await self._handle_response_end()
                            case "client_tool_invocation":
                                await self._handle_tool_invocation(
                                    data.get("toolName"),
                                    data.get("invocationId"),
                                    data.get("parameters"),
                                )
                            case "transcript":
                                match data.get("role"):
                                    case "user":
                                        if data.get("final"):
                                            await self._handle_user_transcript(data.get("text"))
                                    case "agent":
                                        if data.get("final"):
                                            recorder.handle_assistant_final_transcript(
                                                data.get("text") or data.get("delta"),
                                                metadata=_ultravox_message_metadata(data),
                                            )
                                        await self._handle_agent_transcript(
                                            data.get("medium"),
                                            data.get("text"),
                                            data.get("delta"),
                                            data.get("final", False),
                                        )
                    except Exception as exc:
                        if self._disconnecting or not self._socket:
                            return
                        await self.push_error("Ultravox websocket receive error", exc, fatal=True)
            except Exception as exc:
                if self._disconnecting or not self._socket:
                    return
                if self._is_normal_websocket_close(exc):
                    self._emit_normal_websocket_close(exc)
                    self._socket = None
                    return
                await self.push_error("Ultravox websocket receive error", exc, fatal=True)

        async def push_error(self, error_msg: str, exception=None, fatal: bool = False):
            metadata = {
                "error_type": exception.__class__.__name__ if exception else "Unknown",
                "error_message": _sanitize_provider_error(str(exception or error_msg)),
                "fatal": fatal,
            }
            recorder.emit(
                "ultravox.connect_failed" if fatal else "ultravox.error",
                provider="ultravox",
                metadata=metadata,
            )
            await super().push_error(error_msg, exception=exception, fatal=fatal)

    return InstrumentedUltravoxRealtimeLLMService


def _ultravox_message_metadata(data: dict[str, object]) -> dict[str, object]:
    metadata: dict[str, object] = {}
    for key in (
        "type",
        "state",
        "role",
        "medium",
        "final",
        "callId",
        "event",
        "reason",
    ):
        if key in data:
            metadata[key] = data[key]
    text = data.get("text") or data.get("delta")
    if isinstance(text, str) and text:
        metadata["text_preview"] = text[:240]
    return metadata


def _duration_seconds(value: float | int | None) -> str | None:
    if value is None:
        return None
    seconds = max(float(value), 0.0)
    text = f"{seconds:.3f}".rstrip("0").rstrip(".")
    return f"{text or '0'}s"


def _ultravox_vad_settings(settings: Settings) -> dict[str, object]:
    vad_settings: dict[str, object] = {}
    turn_endpoint_delay = _duration_seconds(settings.providers.ultravox_turn_endpoint_delay_seconds)
    if turn_endpoint_delay:
        vad_settings["turnEndpointDelay"] = turn_endpoint_delay
    minimum_turn_duration = _duration_seconds(
        settings.providers.ultravox_minimum_turn_duration_seconds
    )
    if minimum_turn_duration:
        vad_settings["minimumTurnDuration"] = minimum_turn_duration
    minimum_interruption_duration = _duration_seconds(
        settings.providers.ultravox_minimum_interruption_duration_seconds
    )
    if minimum_interruption_duration:
        vad_settings["minimumInterruptionDuration"] = minimum_interruption_duration
    threshold = settings.providers.ultravox_frame_activation_threshold
    if threshold is not None:
        vad_settings["frameActivationThreshold"] = min(max(float(threshold), 0.1), 1.0)
    return vad_settings


def _ultravox_server_websocket_settings(settings: Settings) -> dict[str, object]:
    server_websocket: dict[str, object] = {}
    client_buffer_ms = settings.providers.ultravox_client_buffer_size_ms
    if client_buffer_ms is None:
        return server_websocket
    server_websocket["inputSampleRate"] = 48000
    server_websocket["clientBufferSizeMs"] = min(max(int(client_buffer_ms), 0), 5000)
    return server_websocket


def _build_stt(settings: Settings):
    if settings.providers.stt_provider == "deepgram_flux":
        from pipecat.services.deepgram.flux.stt import DeepgramFluxSTTService

        flux_model = settings.providers.deepgram_model
        if flux_model.startswith("nova-"):
            flux_model = "flux-general-en"
        return DeepgramFluxSTTService(
            api_key=settings.providers.deepgram_api_key,
            should_interrupt=True,
            settings=DeepgramFluxSTTService.Settings(
                model=flux_model or "flux-general-en",
                eager_eot_threshold=settings.providers.deepgram_flux_eager_eot_threshold,
                eot_threshold=settings.providers.deepgram_flux_eot_threshold,
                eot_timeout_ms=settings.providers.deepgram_flux_eot_timeout_ms,
                min_confidence=settings.providers.deepgram_flux_min_confidence,
            ),
        )

    from pipecat.services.deepgram.stt import DeepgramSTTService

    return DeepgramSTTService(
        api_key=settings.providers.deepgram_api_key,
        settings=DeepgramSTTService.Settings(
            model=settings.providers.deepgram_model,
            endpointing=settings.providers.deepgram_endpointing,
            interim_results=True,
            punctuate=True,
            smart_format=True,
            utterance_end_ms=settings.providers.deepgram_utterance_end_ms,
            vad_events=False,
        ),
    )


def _build_llm(settings: Settings, recorder: CallRecorder):
    provider = settings.providers.llm_provider
    if provider == "gemini":
        from pipecat.services.google.llm import GoogleLLMService

        llm_cls = _instrumented_google_llm_service(GoogleLLMService, recorder)
        return llm_cls(
            api_key=settings.providers.google_api_key,
            settings=GoogleLLMService.Settings(
                model=settings.providers.gemini_model,
                system_instruction=settings.prompt.system_prompt,
                max_tokens=settings.prompt.max_tokens,
                temperature=settings.prompt.temperature,
            ),
        )

    if provider == "openai":
        from pipecat.services.openai.llm import OpenAILLMService

        llm_cls = _instrumented_openai_compatible_llm_service(
            OpenAILLMService,
            recorder,
            provider="openai",
        )
        return llm_cls(
            api_key=settings.providers.openai_api_key,
            settings=OpenAILLMService.Settings(
                model=settings.providers.openai_model,
                system_instruction=settings.prompt.system_prompt,
                max_tokens=settings.prompt.max_tokens,
                temperature=settings.prompt.temperature,
            ),
        )

    if provider == "groq":
        from pipecat.services.openai.llm import OpenAILLMService

        llm_cls = _instrumented_openai_compatible_llm_service(
            OpenAILLMService,
            recorder,
            provider="groq",
        )
        return llm_cls(
            api_key=settings.providers.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
            settings=OpenAILLMService.Settings(
                model=settings.providers.groq_model,
                system_instruction=settings.prompt.system_prompt,
                max_tokens=settings.prompt.max_tokens,
                temperature=settings.prompt.temperature,
            ),
        )

    if provider == "qwen":
        from pipecat.services.openai.llm import OpenAILLMService

        llm_cls = _instrumented_openai_compatible_llm_service(
            OpenAILLMService,
            recorder,
            provider="qwen",
        )
        return llm_cls(
            api_key=settings.providers.qwen_api_key,
            base_url=settings.providers.qwen_base_url,
            settings=OpenAILLMService.Settings(
                model=settings.providers.qwen_model,
                system_instruction=settings.prompt.system_prompt,
                max_tokens=settings.prompt.max_tokens,
                temperature=settings.prompt.temperature,
            ),
        )

    if provider == "xai":
        from pipecat.services.openai.llm import OpenAILLMService

        llm_cls = _instrumented_openai_compatible_llm_service(
            OpenAILLMService,
            recorder,
            provider="xai",
        )
        return llm_cls(
            api_key=settings.providers.xai_api_key,
            base_url=settings.providers.xai_base_url,
            settings=OpenAILLMService.Settings(
                model=settings.providers.xai_model,
                system_instruction=settings.prompt.system_prompt,
                max_tokens=settings.prompt.max_tokens,
                temperature=settings.prompt.temperature,
            ),
        )

    if provider == "mock":
        return _build_mock_llm_service(settings.providers.mock_llm_response, recorder)

    raise AgentStartError(f"Unsupported LLM provider: {provider}")


def _build_tts(settings: Settings, recorder: CallRecorder, base_cls, text_aggregation_mode_enum):
    aggregation_mode = _cartesia_text_aggregation_mode(
        text_aggregation_mode_enum,
        settings.voice.tts_text_aggregation_mode,
    )
    text_aggregator = None
    if settings.voice.tts_first_phrase_flush_enabled:
        from verbatim.pipeline.first_phrase import FirstPhraseTextAggregator

        text_aggregator = FirstPhraseTextAggregator(
            recorder=recorder,
            timeout_ms=settings.voice.tts_first_flush_timeout_ms,
            min_words=settings.voice.tts_first_flush_min_words,
            max_words=settings.voice.tts_first_flush_max_words,
            after_first_mode=settings.voice.tts_after_first_mode,
        )

    tts_cls = _cartesia_service_with_buffer_delay(
        base_cls,
        settings.voice.cartesia_max_buffer_delay_ms,
    )
    return tts_cls(
        api_key=settings.providers.cartesia_api_key,
        text_aggregator=text_aggregator,
        text_aggregation_mode=aggregation_mode,
        settings=base_cls.Settings(
            voice=settings.voice.cartesia_voice_id,
            model=settings.voice.cartesia_model,
        ),
    )


def _build_user_turn_strategies(settings: Settings):
    if not settings.session.vad_only_user_turn_start:
        return None
    try:
        from pipecat.turns.user_start.vad_user_turn_start_strategy import VADUserTurnStartStrategy
        from pipecat.turns.user_turn_strategies import UserTurnStrategies

        return UserTurnStrategies(start=[VADUserTurnStartStrategy()])
    except Exception:
        return None


def _build_user_mute_strategies(settings: Settings):
    if not settings.session.mute_user_while_bot_speaking:
        return []
    try:
        from pipecat.turns.user_mute.always_user_mute_strategy import AlwaysUserMuteStrategy

        return [AlwaysUserMuteStrategy()]
    except Exception:
        return []


async def _prewarm_llm_provider(settings: Settings, recorder: CallRecorder) -> None:
    if not settings.session.llm_prewarm_enabled or settings.providers.llm_provider in {
        "mock",
        "ultravox",
    }:
        return

    provider = settings.providers.llm_provider
    model = settings.providers.llm_model
    recorder.emit(
        "llm.prewarm_started",
        provider=provider,
        metadata={"llm_provider": provider, "llm_model": model},
    )
    try:
        await asyncio.wait_for(_run_llm_prewarm(settings), timeout=1.0)
    except Exception as exc:
        recorder.emit(
            "llm.prewarm_failed",
            provider=provider,
            metadata={
                "llm_provider": provider,
                "llm_model": model,
                "error_type": exc.__class__.__name__,
                "error_message": str(exc)[:240],
            },
        )
        return
    recorder.emit(
        "llm.prewarm_completed",
        provider=provider,
        metadata={"llm_provider": provider, "llm_model": model},
    )


async def _run_llm_prewarm(settings: Settings) -> None:
    provider = settings.providers.llm_provider
    if provider == "gemini":
        await _prewarm_gemini(settings)
        return
    if provider in {"openai", "groq", "qwen", "xai"}:
        await _prewarm_openai_compatible(settings)


async def _prewarm_openai_compatible(settings: Settings) -> None:
    import httpx

    provider = settings.providers.llm_provider
    api_key_by_provider = {
        "openai": settings.providers.openai_api_key,
        "groq": settings.providers.groq_api_key,
        "qwen": settings.providers.qwen_api_key,
        "xai": settings.providers.xai_api_key,
    }
    api_key = api_key_by_provider.get(provider)
    if not api_key:
        return
    base_url_by_provider = {
        "openai": "https://api.openai.com/v1",
        "groq": "https://api.groq.com/openai/v1",
        "qwen": settings.providers.qwen_base_url,
        "xai": settings.providers.xai_base_url,
    }
    base_url = base_url_by_provider[provider]
    async with httpx.AsyncClient(timeout=httpx.Timeout(1.0, connect=0.5)) as client:
        async with client.stream(
            "POST",
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": settings.providers.llm_model,
                "messages": [{"role": "user", "content": "warmup"}],
                "max_tokens": 1,
                "temperature": 0,
                "stream": True,
            },
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data:") and "[DONE]" not in line:
                    return


async def _prewarm_gemini(settings: Settings) -> None:
    import httpx

    if not settings.providers.google_api_key:
        return
    model = settings.providers.gemini_model
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:streamGenerateContent"
    )
    async with httpx.AsyncClient(timeout=httpx.Timeout(1.0, connect=0.5)) as client:
        async with client.stream(
            "POST",
            url,
            params={"key": settings.providers.google_api_key, "alt": "sse"},
            json={
                "contents": [{"role": "user", "parts": [{"text": "warmup"}]}],
                "generationConfig": {"maxOutputTokens": 1, "temperature": 0},
            },
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    return


def _cartesia_text_aggregation_mode(text_aggregation_mode_enum, configured: str):
    name = configured.upper()
    return getattr(text_aggregation_mode_enum, name, text_aggregation_mode_enum.SENTENCE)


def _cartesia_service_with_buffer_delay(base_cls, max_buffer_delay_ms: int | None):
    if max_buffer_delay_ms is None:
        return base_cls

    buffer_delay = min(max(int(max_buffer_delay_ms), 0), 5000)

    class BufferedCartesiaTTSService(base_cls):
        def _build_msg(
            self,
            text: str = "",
            continue_transcript: bool = True,
            add_timestamps: bool = True,
            context_id: str = "",
        ):
            payload = json.loads(
                super()._build_msg(
                    text=text,
                    continue_transcript=continue_transcript,
                    add_timestamps=add_timestamps,
                    context_id=context_id,
                )
            )
            payload["max_buffer_delay_ms"] = buffer_delay
            return json.dumps(payload)

    return BufferedCartesiaTTSService


def _build_transport(settings: Settings, session: AgentSession):
    provider = (session.transport_provider or settings.providers.transport_provider or "daily").lower()
    if provider == "livekit":
        try:
            from pipecat.transports.livekit.transport import LiveKitParams, LiveKitTransport
        except ImportError:
            from pipecat.transports.services.livekit import LiveKitParams, LiveKitTransport

        if not session.room_name:
            raise AgentStartError("room_name is required for LiveKit transport.")
        if not session.room_token:
            raise AgentStartError("room_token is required for LiveKit transport.")
        return LiveKitTransport(
            session.room_url,
            session.room_token,
            session.room_name,
            LiveKitParams(
                audio_in_enabled=True,
                audio_in_sample_rate=settings.providers.livekit_audio_in_sample_rate,
                audio_out_enabled=True,
                audio_out_sample_rate=settings.providers.livekit_audio_out_sample_rate,
                audio_out_bitrate=settings.providers.livekit_audio_out_bitrate,
                audio_out_10ms_chunks=min(
                    max(int(settings.providers.livekit_audio_out_10ms_chunks), 1),
                    10,
                ),
                audio_out_auto_silence=settings.providers.livekit_audio_out_auto_silence,
                video_in_enabled=False,
                video_out_enabled=False,
            ),
        )

    try:
        from pipecat.transports.services.daily import DailyParams, DailyTransport
    except ImportError:
        from pipecat.transports.daily.transport import DailyParams, DailyTransport

    return DailyTransport(
        session.room_url,
        session.room_token,
        settings.session.bot_name,
        DailyParams(
            api_key=settings.providers.daily_api_key or "",
            audio_in_enabled=True,
            audio_out_enabled=True,
            camera_out_enabled=False,
        ),
    )


def _instrumented_google_llm_service(base_cls, recorder: CallRecorder):
    class InstrumentedGoogleLLMService(base_cls):
        async def _stream_content(self, params):
            response = await super()._stream_content(params)

            async def wrapped_response():
                async for chunk in response:
                    text = _first_text_from_gemini_chunk(chunk)
                    if text:
                        recorder.handle_llm_stream_chunk(
                            text,
                            {
                                "source": "gemini_stream_chunk",
                                "chunk_type": chunk.__class__.__name__,
                            },
                        )
                    yield chunk

            return wrapped_response()

    return InstrumentedGoogleLLMService


def _instrumented_openai_compatible_llm_service(
    base_cls,
    recorder: CallRecorder,
    *,
    provider: str,
):
    class InstrumentedOpenAICompatibleLLMService(base_cls):
        async def push_error(self, error_msg: str, exception=None, fatal: bool = False):
            if fatal:
                await super().push_error(error_msg, exception=exception, fatal=fatal)
                return

            fallback_text = _llm_provider_fallback_text(provider)
            recorder.emit(
                "llm.error_recovered",
                turn_id=recorder.current_turn_id,
                provider=provider,
                metadata={
                    "llm_provider": provider,
                    "llm_model": recorder.llm_model,
                    "error_category": _provider_error_category(error_msg),
                    "error_preview": _sanitize_provider_error(error_msg),
                    "fallback_text": fallback_text,
                    "recovery_hook": "llm.push_error",
                },
            )
            try:
                await self.stop_ttfb_metrics()
            except Exception:
                pass
            await self._push_llm_text(fallback_text)

        async def _stream_chat_completions_specific_context(self, context):
            stream = await super()._stream_chat_completions_specific_context(context)
            return _wrap_openai_compatible_stream(stream, recorder, provider)

        async def _stream_chat_completions_universal_context(self, context):
            stream = await super()._stream_chat_completions_universal_context(context)
            return _wrap_openai_compatible_stream(stream, recorder, provider)

    return InstrumentedOpenAICompatibleLLMService


def _wrap_openai_compatible_stream(stream, recorder: CallRecorder, provider: str):
    async def wrapped_response():
        async for chunk in stream:
            text = _first_text_from_openai_chunk(chunk)
            if text:
                recorder.handle_llm_stream_chunk(
                    text,
                    {
                        "source": f"{provider}_stream_chunk",
                        "chunk_type": chunk.__class__.__name__,
                    },
                )
            yield chunk

    return wrapped_response()


def _llm_provider_fallback_text(provider: str) -> str:
    if provider == "xai":
        return "One sec, Grok is not ready."
    if provider == "qwen":
        return "One sec, Qwen is not ready."
    if provider == "groq":
        return "One sec, Groq is not responding."
    if provider == "openai":
        return "One sec, OpenAI is not responding."
    return "One sec, this model is not ready."


def _provider_error_category(error_text: str) -> str:
    lowered = error_text.lower()
    if "credit" in lowered or "license" in lowered or "billing" in lowered:
        return "provider_billing_or_access"
    if "403" in lowered or "permission" in lowered or "unauthorized" in lowered:
        return "provider_permission"
    if "rate limit" in lowered or "429" in lowered:
        return "provider_rate_limit"
    if "timeout" in lowered:
        return "provider_timeout"
    return "provider_error"


def _sanitize_provider_error(error_text: str) -> str:
    sanitized = re.sub(r"https?://\S+", "[url]", error_text)
    sanitized = re.sub(r"sk-[A-Za-z0-9_-]+", "[redacted]", sanitized)
    sanitized = re.sub(r"team/[A-Za-z0-9_-]+", "team/[redacted]", sanitized)
    return sanitized[:240]


def _first_text_from_openai_chunk(chunk) -> str | None:
    choices = getattr(chunk, "choices", None) or []
    if not choices:
        return None
    delta = getattr(choices[0], "delta", None)
    if not delta:
        return None
    content = getattr(delta, "content", None)
    if content:
        return str(content)
    audio = getattr(delta, "audio", None)
    if isinstance(audio, dict) and audio.get("transcript"):
        return str(audio["transcript"])
    return None


def _build_mock_llm_service(response_text: str, recorder: CallRecorder):
    from pipecat.frames.frames import (
        LLMContextFrame,
        LLMFullResponseEndFrame,
        LLMFullResponseStartFrame,
        LLMMessagesFrame,
        LLMTextFrame,
    )
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    class MockLLMService(FrameProcessor):
        def __init__(self) -> None:
            super().__init__(name="MockLLMService")

        async def process_frame(self, frame, direction: FrameDirection):
            await super().process_frame(frame, direction)
            if isinstance(frame, (LLMContextFrame, LLMMessagesFrame)):
                await self.push_frame(LLMFullResponseStartFrame(), direction)
                recorder.handle_llm_raw_token(
                    response_text,
                    {
                        "source": "mock_stream_chunk",
                        "chunk_type": "MockLLMChunk",
                    },
                )
                await self.push_frame(LLMTextFrame(response_text), direction)
                await self.push_frame(LLMFullResponseEndFrame(), direction)
                return
            await self.push_frame(frame, direction)

    return MockLLMService()


def _first_text_from_gemini_chunk(chunk) -> str | None:
    for candidate in getattr(chunk, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            text = getattr(part, "text", None)
            if text and not getattr(part, "thought", False):
                return str(text)
    return None


def _register_transport_handlers(transport, recorder: CallRecorder, *, provider: str) -> None:
    if provider == "livekit":
        _register_livekit_transport_handlers(transport, recorder)
        return
    _register_daily_transport_handlers(transport, recorder)


def _register_daily_transport_handlers(transport, recorder: CallRecorder) -> None:
    @transport.event_handler("on_joined")
    async def on_joined(_transport, data):
        recorder.handle_transport_event("transport.bot_joined", metadata={"data": str(data)})

    @transport.event_handler("on_connected")
    async def on_connected(_transport, data):
        recorder.handle_transport_event("transport.connected", metadata={"data": str(data)})

    @transport.event_handler("on_left")
    async def on_left(_transport):
        recorder.handle_transport_event("transport.bot_left")

    @transport.event_handler("on_error")
    async def on_error(_transport, error):
        recorder.handle_transport_event(
            "transport.error",
            metadata={"error_type": error.__class__.__name__, "error_message": str(error)},
        )

    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(_transport, participant):
        recorder.handle_transport_event(
            "transport.client_connected",
            metadata={"participant": str(participant), "first": True},
        )

    @transport.event_handler("on_participant_joined")
    async def on_participant_joined(_transport, participant):
        recorder.handle_transport_event(
            "transport.client_connected",
            metadata={"participant": str(participant)},
        )

    @transport.event_handler("on_participant_left")
    async def on_participant_left(_transport, participant, reason=None):
        recorder.handle_transport_event(
            "transport.client_disconnected",
            metadata={"participant": str(participant), "reason": str(reason)},
        )


def _register_livekit_transport_handlers(transport, recorder: CallRecorder) -> None:
    @transport.event_handler("on_connected")
    async def on_connected(_transport):
        recorder.handle_transport_event("transport.connected", provider="livekit")

    @transport.event_handler("on_disconnected")
    async def on_disconnected(_transport):
        recorder.handle_transport_event("transport.bot_left", provider="livekit")

    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(_transport, participant_id):
        recorder.handle_transport_event(
            "transport.client_connected",
            provider="livekit",
            metadata={"participant": str(participant_id), "first": True},
        )

    @transport.event_handler("on_participant_connected")
    async def on_participant_connected(_transport, participant_id):
        recorder.handle_transport_event(
            "transport.client_connected",
            provider="livekit",
            metadata={"participant": str(participant_id)},
        )

    @transport.event_handler("on_participant_disconnected")
    async def on_participant_disconnected(_transport, participant_id):
        recorder.handle_transport_event(
            "transport.client_disconnected",
            provider="livekit",
            metadata={"participant": str(participant_id), "reason": "disconnected"},
        )

    @transport.event_handler("on_participant_left")
    async def on_participant_left(_transport, participant_id, reason=None):
        recorder.handle_transport_event(
            "transport.client_disconnected",
            provider="livekit",
            metadata={"participant": str(participant_id), "reason": str(reason)},
        )

    @transport.event_handler("on_audio_track_subscribed")
    async def on_audio_track_subscribed(_transport, participant_id):
        recorder.handle_transport_event(
            "transport.audio_subscribed",
            provider="livekit",
            metadata={"participant": str(participant_id)},
        )


def _register_stt_handlers(stt, recorder: CallRecorder, task_ref: dict[str, object] | None = None) -> None:
    def transcript_metadata(args) -> dict[str, str]:
        transcript = args[-1] if args else None
        return {"transcript": str(transcript)} if transcript is not None else {}

    try:
        @stt.event_handler("on_start_of_turn")
        async def on_start_of_turn(*args):
            turn_id = recorder.ensure_turn()
            recorder.emit(
                "user.speech_started",
                turn_id=turn_id,
                provider="deepgram_flux",
                metadata=transcript_metadata(args),
                once_per_turn=True,
            )
            recorder.emit(
                "stt.start_of_turn",
                turn_id=turn_id,
                provider="deepgram_flux",
                metadata=transcript_metadata(args),
            )

        @stt.event_handler("on_eager_end_of_turn")
        async def on_eager_end_of_turn(*args):
            turn_id = recorder.ensure_turn()
            recorder.emit(
                "stt.eager_end_of_turn",
                turn_id=turn_id,
                provider="deepgram_flux",
                metadata=transcript_metadata(args),
                once_per_turn=True,
            )

        @stt.event_handler("on_end_of_turn")
        async def on_end_of_turn(*args):
            turn_id = recorder.ensure_turn()
            recorder.emit(
                "stt.utterance_end",
                turn_id=turn_id,
                provider="deepgram_flux",
                metadata=transcript_metadata(args),
                once_per_turn=True,
            )

        @stt.event_handler("on_turn_resumed")
        async def on_turn_resumed(*args):
            turn_id = recorder.ensure_turn()
            recorder.emit(
                "stt.turn_resumed",
                turn_id=turn_id,
                provider="deepgram_flux",
                metadata=transcript_metadata(args),
            )
            if recorder.has_seen_event(turn_id, "stt.eager_end_of_turn"):
                recorder.cancel_active_generation(reason="flux_turn_resumed", turn_id=turn_id)
                recorder.emit(
                    "turn.eager_cancelled",
                    turn_id=turn_id,
                    provider="deepgram_flux",
                    metadata=transcript_metadata(args),
                    once_per_turn=True,
                )
                task = task_ref.get("task") if task_ref else None
                if task is not None:
                    try:
                        from pipecat.frames.frames import InterruptionTaskFrame
                        from pipecat.processors.frame_processor import FrameDirection

                        await task.queue_frame(InterruptionTaskFrame(), FrameDirection.UPSTREAM)
                    except Exception as exc:
                        recorder.emit(
                            "pipeline.interruption_error",
                            turn_id=turn_id,
                            provider="pipeline",
                            metadata={
                                "error_type": exc.__class__.__name__,
                                "error_message": str(exc),
                            },
                        )
    except Exception:
        return


def _register_transcript_handlers(user_aggregator, assistant_aggregator, recorder: CallRecorder) -> None:
    @user_aggregator.event_handler("on_user_turn_stopped")
    async def on_user_turn_stopped(_aggregator, strategy, message):
        content = getattr(message, "content", None)
        recorder.handle_user_turn_stopped(
            content,
            metadata={"strategy": str(strategy), "message": str(message)},
        )

    @assistant_aggregator.event_handler("on_assistant_turn_stopped")
    async def on_assistant_turn_stopped(_aggregator, message):
        content = getattr(message, "content", None)
        interrupted = bool(getattr(message, "interrupted", False))
        recorder.handle_assistant_turn_stopped(
            content,
            interrupted=interrupted,
            metadata={"message": str(message)},
        )


def _register_tts_handlers(tts, recorder: CallRecorder) -> None:
    @tts.event_handler("on_tts_request")
    async def on_tts_request(_tts, context_id, text):
        recorder.handle_tts_request(str(context_id), str(text))


def _register_task_handlers(task, recorder: CallRecorder, greeting: str | None = None) -> None:
    @task.event_handler("on_pipeline_started")
    async def on_pipeline_started(_task, frame):
        recorder.emit("pipeline.started", metadata={"frame": frame.__class__.__name__})
        if greeting:
            asyncio.create_task(_queue_greeting(_task, recorder, greeting))

    @task.event_handler("on_pipeline_finished")
    async def on_pipeline_finished(_task, frame):
        recorder.emit("pipeline.finished", metadata={"frame": frame.__class__.__name__})


async def _queue_greeting(task, recorder: CallRecorder, greeting: str) -> None:
    try:
        from pipecat.frames.frames import TTSSpeakFrame

        await asyncio.sleep(0.25)
        await task.queue_frame(TTSSpeakFrame(greeting))
        recorder.emit(
            "assistant.greeting_queued",
            provider="pipeline",
            metadata={"text_preview": greeting[:120]},
        )
    except Exception as exc:
        recorder.emit(
            "assistant.greeting_failed",
            provider="pipeline",
            metadata={"error_type": exc.__class__.__name__, "error_message": str(exc)[:240]},
        )


def _setup_otel_if_enabled(settings: Settings) -> None:
    if not settings.instrumentation.enable_otel:
        return
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from pipecat.utils.tracing.setup import setup_tracing

        exporter = OTLPSpanExporter(
            endpoint=settings.instrumentation.otel_exporter_otlp_endpoint,
            insecure=True,
        )
        setup_tracing(
            service_name="verbatim-voice-pipeline",
            exporter=exporter,
            console_export=False,
        )
    except Exception:
        # The local JSONL path remains the source of truth if optional OTel setup is unavailable.
        return


def _setup_provider_log_redaction() -> None:
    if getattr(_setup_provider_log_redaction, "_configured", False):
        return
    try:
        from loguru import logger as loguru_logger
    except Exception:
        return

    auth_pattern = re.compile(
        r"(Authorization['\"]?: ['\"]Token )[^'\"]+|(\"Authorization\":\\s*\"Token )[^\"]+",
        re.IGNORECASE,
    )

    def redacting_sink(message) -> None:
        text = auth_pattern.sub(lambda match: f"{match.group(1) or match.group(2)}[redacted]", str(message))
        sys.stderr.write(text)

    loguru_logger.remove()
    loguru_logger.add(redacting_sink, level="DEBUG", colorize=True)
    setattr(_setup_provider_log_redaction, "_configured", True)
