from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import re
import sys
import time
import uuid
from typing import Any

from verbatim.config import Settings
from verbatim.events import EventSink


@dataclass(frozen=True)
class AgentSession:
    transport_provider: str
    room_url: str
    room_token: str | None = None
    room_name: str | None = None
    call_id: str | None = None
    session_id: str | None = None
    client_id: str | None = None
    caller_phone: str | None = None
    knowledge_base: str | None = None
    tools_enabled: bool = False


class AgentStartError(RuntimeError):
    pass


def _session_system_prompt(base_prompt: str, session: AgentSession) -> str:
    parts = [base_prompt.strip()]
    call_context = _session_call_context_prompt(session)
    if call_context:
        parts.append(call_context)
    return "\n\n".join(part for part in parts if part)


def _session_context_messages(base_prompt: str, session: AgentSession) -> list[dict[str, str]]:
    call_context = _session_call_context_prompt(session)
    if call_context:
        return [{"role": "system", "content": call_context}]
    return [{"role": "system", "content": base_prompt}]


def _session_call_context_prompt(session: AgentSession) -> str | None:
    parts: list[str] = []
    kb = _bounded_call_context(session.knowledge_base, max_chars=6000)
    if kb:
        parts.append(
            "Call knowledge base for this call only. Use it when relevant, but do not mention these notes exist.\n"
            f"{kb}"
        )
    return "\n\n".join(parts) or None


def _bounded_call_context(value: str | None, *, max_chars: int) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\n{3,}", "\n\n", value.strip())
    if not cleaned:
        return None
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[:max_chars].rstrip()}\n[truncated]"


class PipelineRecorder:
    def __init__(self, settings: Settings, sink: EventSink) -> None:
        self.settings = settings
        self.sink = sink
        self.turn_index = 0
        self.current_turn_id: str | None = None
        self.turn_seen: dict[str, set[str]] = {}
        self.call_seen: set[str] = set()
        self.last_user_speech_started_at_ms: float | None = None
        self.last_user_speech_stopped_at_ms: float | None = None
        self.latest_user_text: str | None = None
        self.recent_user_texts: list[str] = []

    @property
    def llm_provider(self) -> str:
        return self.settings.providers.llm_provider

    @property
    def llm_model(self) -> str:
        return self.settings.providers.llm_model

    def emit(
        self,
        event_name: str,
        *,
        provider: str = "pipeline",
        turn_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        once_per_turn: bool = False,
        use_current_turn: bool = True,
    ) -> dict[str, Any]:
        resolved_turn_id = turn_id if turn_id is not None else (self.current_turn_id if use_current_turn else None)
        if once_per_turn and resolved_turn_id:
            seen = self.turn_seen.setdefault(resolved_turn_id, set())
            if event_name in seen:
                return {}
            seen.add(event_name)
        return self.sink.emit(event_name, provider=provider, turn_id=resolved_turn_id, metadata=metadata or {})

    def next_turn(self) -> str:
        self.turn_index += 1
        self.current_turn_id = f"turn_{self.turn_index:04d}"
        self.turn_seen.setdefault(self.current_turn_id, set())
        return self.current_turn_id

    def handle_llm_request_started(self, metadata: dict[str, Any] | None = None) -> None:
        self.emit(
            "llm.request_started",
            provider=self.llm_provider,
            metadata={"llm_provider": self.llm_provider, "llm_model": self.llm_model, **(metadata or {})},
            once_per_turn=True,
        )

    def handle_llm_stream_chunk(self, text: str, metadata: dict[str, Any] | None = None) -> None:
        if not text:
            return
        self.emit(
            "llm.first_token",
            provider=self.llm_provider,
            metadata={
                "llm_provider": self.llm_provider,
                "llm_model": self.llm_model,
                "text_preview": text[:160],
                **(metadata or {}),
            },
            once_per_turn=True,
        )

    def handle_frame(self, stage: str, frame: Any) -> None:
        frame_type = frame.__class__.__name__
        metadata = {"frame_type": frame_type, "stage": stage}
        if stage == "stt" and frame_type in {"UserStartedSpeakingFrame", "VADUserStartedSpeakingFrame"}:
            event = self.emit(
                "user.speech.started",
                provider=self.settings.providers.transport_provider,
                metadata={
                    **metadata,
                    "start_secs": getattr(frame, "start_secs", None),
                    "emulated": getattr(frame, "emulated", None),
                },
                use_current_turn=False,
            )
            self.last_user_speech_started_at_ms = event.get("timestamp_monotonic_ms") or round(time.monotonic() * 1000, 3)
            self.last_user_speech_stopped_at_ms = None
            return
        if stage == "stt" and frame_type in {"UserStoppedSpeakingFrame", "VADUserStoppedSpeakingFrame"}:
            event = self.emit(
                "user.speech.stopped",
                provider=self.settings.providers.transport_provider,
                metadata={
                    **metadata,
                    "stop_secs": getattr(frame, "stop_secs", None),
                    "emulated": getattr(frame, "emulated", None),
                },
                use_current_turn=False,
            )
            self.last_user_speech_stopped_at_ms = event.get("timestamp_monotonic_ms") or round(time.monotonic() * 1000, 3)
            return
        if stage == "input" and frame_type in {"InputAudioRawFrame", "UserAudioRawFrame"}:
            if "audio.input.first_frame" not in self.call_seen:
                self.call_seen.add("audio.input.first_frame")
                self.emit(
                    "audio.input_first_frame",
                    provider=self.settings.providers.transport_provider,
                    metadata={
                        **metadata,
                        "sample_rate": getattr(frame, "sample_rate", None),
                        "num_channels": getattr(frame, "num_channels", None),
                        "audio_bytes": len(getattr(frame, "audio", b"") or b""),
                        "user_id": getattr(frame, "user_id", None),
                    },
                )
            return
        if frame_type == "TranscriptionFrame":
            text = _frame_text(frame)
            if text:
                turn_id = self.next_turn()
                self.latest_user_text = text
                self.recent_user_texts.append(text)
                self.recent_user_texts = self.recent_user_texts[-8:]
                transcript_at_ms = round(time.monotonic() * 1000, 3)
                stt_metadata = {
                    "user_speech_started_at_ms": self.last_user_speech_started_at_ms,
                    "user_speech_stopped_at_ms": self.last_user_speech_stopped_at_ms,
                }
                if self.last_user_speech_stopped_at_ms is not None:
                    stt_metadata["stt_processing_ms"] = round(transcript_at_ms - self.last_user_speech_stopped_at_ms, 1)
                self.emit(
                    "transcript.user",
                    provider=self.settings.providers.stt_provider,
                    turn_id=turn_id,
                    metadata={**metadata, "text": text, **stt_metadata},
                )
            return
        if frame_type == "LLMTextFrame":
            text = _frame_text(frame)
            self.handle_llm_stream_chunk(text, {"source": "llm_text_frame", **metadata})
            return
        if frame_type == "TTSAudioRawFrame":
            self.emit("tts.first_audio", provider="cartesia", metadata=metadata, once_per_turn=True)
            self.emit(
                "assistant.playback_started",
                provider=self.sink.agent_id,
                metadata=metadata,
                once_per_turn=True,
            )
            return
        if frame_type == "BotStoppedSpeakingFrame":
            self.emit("assistant.completed", provider=self.sink.agent_id, metadata=metadata, once_per_turn=True)
            return
        if frame_type == "ErrorFrame":
            self.emit("error", metadata={**metadata, "error": str(frame)[:240]}, once_per_turn=True)

    def handle_tts_request(self, context_id: str, text: str) -> None:
        self.emit(
            "tts.request_started",
            provider="cartesia",
            metadata={
                "context_id": context_id,
                "text_preview": text[:160],
                "tts_model": self.settings.voice.cartesia_model,
            },
            once_per_turn=True,
        )


async def run_voice_agent(settings: Settings, session: AgentSession) -> None:
    missing = settings.missing_agent_keys()
    if missing:
        raise AgentStartError(f"Missing required agent environment variables: {', '.join(missing)}")
    sink = EventSink(
        settings.instrumentation.event_log_path,
        settings.instrumentation.transcript_dir,
        settings.instrumentation.call_summary_dir,
        session_id=session.session_id or "",
        call_id=session.call_id or "",
        agent_id=settings.agent.agent_id,
        client_id=session.client_id or settings.integrations.default_client_id or settings.agent.client_id,
        enabled=settings.instrumentation.enable_jsonl_events,
    )
    recorder = PipelineRecorder(settings, sink)
    recorder.emit("session.created", metadata={"transport_provider": session.transport_provider})
    recorder.emit(
        "session.configured",
        metadata={
            "transport_provider": session.transport_provider,
            "room_name": session.room_name,
            "client_id": session.client_id or settings.integrations.default_client_id,
            "caller_phone_configured": bool(session.caller_phone),
            "knowledge_base_configured": bool(session.knowledge_base),
            "knowledge_base_chars": len(session.knowledge_base or ""),
            "tools_enabled": session.tools_enabled,
            "stt_provider": "ultravox" if settings.providers.llm_provider == "ultravox" else settings.providers.stt_provider,
            "stt_model": settings.providers.ultravox_model if settings.providers.llm_provider == "ultravox" else settings.providers.deepgram_model,
            "llm_provider": settings.providers.llm_provider,
            "llm_model": settings.providers.llm_model,
            "tts_provider": "ultravox" if settings.providers.llm_provider == "ultravox" else "cartesia",
            "tts_model": settings.providers.ultravox_model if settings.providers.llm_provider == "ultravox" else settings.voice.cartesia_model,
        },
    )
    try:
        _setup_provider_log_redaction()
        from pipecat.pipeline.pipeline import Pipeline
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineParams, PipelineTask

        if settings.providers.llm_provider == "ultravox":
            await _run_ultravox_pipeline(settings, session, recorder, Pipeline, PipelineRunner, PipelineParams, PipelineTask)
        else:
            await _run_cascade_pipeline(settings, session, recorder, Pipeline, PipelineRunner, PipelineParams, PipelineTask)
        recorder.emit("session.ended", metadata={"outcome": "completed"})
        sink.write_summary({"call_id": session.call_id, "session_id": session.session_id, "outcome": "completed"})
    except asyncio.CancelledError:
        recorder.emit("session.ended", metadata={"outcome": "cancelled"})
        sink.write_summary({"call_id": session.call_id, "session_id": session.session_id, "outcome": "cancelled"})
        raise
    except Exception as exc:
        recorder.emit(
            "error",
            metadata={"error_type": exc.__class__.__name__, "error_message": str(exc)[:240]},
        )
        recorder.emit("session.ended", metadata={"outcome": "failed"})
        sink.write_summary({"call_id": session.call_id, "session_id": session.session_id, "outcome": "failed"})
        raise


async def _run_cascade_pipeline(settings, session, recorder, Pipeline, PipelineRunner, PipelineParams, PipelineTask) -> None:
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair, LLMUserAggregatorParams
    from pipecat.services.cartesia.tts import CartesiaTTSService
    from pipecat.services.tts_service import TextAggregationMode

    vad_analyzer = SileroVADAnalyzer()
    transport = _build_transport(settings, session)
    stt = _build_stt(settings)
    llm = _build_llm(settings, recorder)
    tts = _build_tts(settings, recorder, CartesiaTTSService, TextAggregationMode)
    context = LLMContext(messages=_session_context_messages(settings.prompt.system_prompt, session))
    tools_schema = None
    if session.tools_enabled:
        from verbatim.integrations.tools import configure_scheduling_tools

        tools_schema = configure_scheduling_tools(settings, session, recorder, llm, context)
        recorder.emit(
            "tool.schema.configured",
            provider="tool",
            metadata={
                "client_id": session.client_id or settings.integrations.default_client_id,
                "tools_enabled": bool(tools_schema),
                "integration_provider": "verbatim",
                "integration_key": "safe-tool-surface",
                "activation": "calendar_and_followup_turns_only",
            },
        )
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=vad_analyzer,
            user_turn_stop_timeout=settings.session.user_turn_stop_timeout,
        ),
    )
    _register_transport_handlers(transport, recorder, provider=session.transport_provider)
    _register_tts_handlers(tts, recorder)
    pipeline = Pipeline(
        [
            transport.input(),
            _probe("input", recorder),
            stt,
            _probe("stt", recorder),
            user_aggregator,
            _calendar_action(settings, session, recorder),
            _tool_gate(settings, session, recorder, tools_schema),
            _probe("pre_llm", recorder),
            llm,
            _probe("llm", recorder),
            _identity_bleed_guard(recorder),
            tts,
            _probe("tts", recorder),
            transport.output(),
            _probe("output", recorder),
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
    _register_task_handlers(task, recorder, greeting=settings.prompt.greeting)
    await PipelineRunner(handle_sigint=False).run(task)


def _tool_gate(settings: Settings, session: AgentSession, recorder: PipelineRecorder, tools_schema):
    from verbatim.integrations.tools import create_tool_gate_processor

    return create_tool_gate_processor(settings, session, recorder, tools_schema)


def _calendar_action(settings: Settings, session: AgentSession, recorder: PipelineRecorder):
    from verbatim.integrations.tools import create_calendar_action_processor

    return create_calendar_action_processor(settings, session, recorder)


async def _run_ultravox_pipeline(settings, session, recorder, Pipeline, PipelineRunner, PipelineParams, PipelineTask) -> None:
    if session.transport_provider != "livekit":
        raise AgentStartError("UltraVox realtime mode requires LiveKit transport.")
    transport = _build_transport(settings, session)
    ultravox = _build_ultravox_realtime_service(settings, session, recorder)
    _register_transport_handlers(transport, recorder, provider=session.transport_provider)
    pipeline = Pipeline(
        [
            transport.input(),
            _probe("input", recorder),
            ultravox,
            _probe("ultravox", recorder),
            transport.output(),
            _probe("output", recorder),
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
    _register_task_handlers(task, recorder, greeting=None)
    await PipelineRunner(handle_sigint=False).run(task)


def _probe(name: str, recorder: PipelineRecorder):
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    class Probe(FrameProcessor):
        def __init__(self) -> None:
            super().__init__(name=f"v2-{name}-probe")

        async def process_frame(self, frame, direction: FrameDirection):
            await super().process_frame(frame, direction)
            recorder.handle_frame(name, frame)
            await self.push_frame(frame, direction)

    return Probe()


def _identity_bleed_guard(recorder: PipelineRecorder):
    from pipecat.frames.frames import LLMTextFrame
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    blocked_terms = ["du" + "bai", "cr" + "tg", "ali" + "cia"]
    fallback = "I help with real estate questions. What would you like to know?"

    class IdentityBleedGuard(FrameProcessor):
        def __init__(self) -> None:
            super().__init__(name="v2-identity-bleed-guard")

        async def process_frame(self, frame, direction: FrameDirection):
            await super().process_frame(frame, direction)
            if isinstance(frame, LLMTextFrame):
                text = _frame_text(frame)
                lowered = text.lower()
                if any(term in lowered for term in blocked_terms):
                    recorder.emit(
                        "llm.identity_bleed_blocked",
                        provider=recorder.llm_provider,
                        metadata={"llm_provider": recorder.llm_provider, "llm_model": recorder.llm_model},
                    )
                    frame.text = fallback
            await self.push_frame(frame, direction)

    return IdentityBleedGuard()


def _build_transport(settings: Settings, session: AgentSession):
    provider = session.transport_provider
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
                audio_out_10ms_chunks=min(max(int(settings.providers.livekit_audio_out_10ms_chunks), 1), 10),
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


def _build_stt(settings: Settings):
    if settings.providers.stt_provider == "deepgram_flux":
        from pipecat.services.deepgram.flux.stt import DeepgramFluxSTTService

        model = settings.providers.deepgram_model or "flux-general-en"
        if model.startswith("nova-"):
            model = "flux-general-en"
        return DeepgramFluxSTTService(
            api_key=settings.providers.deepgram_api_key,
            should_interrupt=True,
            settings=DeepgramFluxSTTService.Settings(
                model=model,
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


def _build_llm(settings: Settings, recorder: PipelineRecorder):
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
    if provider in {"openai", "groq", "qwen", "xai"}:
        from pipecat.services.openai.llm import OpenAILLMService

        base_urls = {
            "openai": None,
            "groq": "https://api.groq.com/openai/v1",
            "qwen": settings.providers.qwen_base_url,
            "xai": settings.providers.xai_base_url,
        }
        api_keys = {
            "openai": settings.providers.openai_api_key,
            "groq": settings.providers.groq_api_key,
            "qwen": settings.providers.qwen_api_key,
            "xai": settings.providers.xai_api_key,
        }
        llm_cls = _instrumented_openai_compatible_llm_service(OpenAILLMService, recorder, provider=provider)
        kwargs = {
            "api_key": api_keys[provider],
            "settings": OpenAILLMService.Settings(
                model=settings.providers.llm_model,
                system_instruction=settings.prompt.system_prompt,
                max_tokens=settings.prompt.max_tokens,
                temperature=settings.prompt.temperature,
            ),
        }
        if base_urls[provider]:
            kwargs["base_url"] = base_urls[provider]
        return llm_cls(**kwargs)
    if provider == "mock":
        return _build_mock_llm_service(settings.providers.mock_llm_response, recorder)
    raise AgentStartError(f"Unsupported LLM provider: {provider}")


def _build_tts(settings: Settings, recorder: PipelineRecorder, base_cls, text_aggregation_mode_enum):
    aggregation_mode = _cartesia_text_aggregation_mode(text_aggregation_mode_enum, settings.voice.tts_text_aggregation_mode)
    tts_cls = _cartesia_service_with_buffer_delay(base_cls, settings.voice.cartesia_max_buffer_delay_ms)
    return tts_cls(
        api_key=settings.providers.cartesia_api_key,
        text_aggregation_mode=aggregation_mode,
        settings=base_cls.Settings(
            voice=settings.voice.cartesia_voice_id,
            model=settings.voice.cartesia_model,
        ),
    )


def _build_ultravox_realtime_service(settings: Settings, session: AgentSession, recorder: PipelineRecorder):
    from pipecat.services.ultravox.llm import OneShotInputParams, UltravoxRealtimeLLMService

    voice = uuid.UUID(settings.providers.ultravox_voice_id) if settings.providers.ultravox_voice_id else None
    cls = _instrumented_ultravox_service(UltravoxRealtimeLLMService, recorder)
    return cls(
        api_key=settings.providers.ultravox_api_key or "",
        model=settings.providers.ultravox_model,
        voice=voice,
        temperature=settings.prompt.temperature,
        max_duration=settings.providers.ultravox_max_duration_seconds,
        system_prompt=_session_system_prompt(settings.prompt.system_prompt, session),
        initial_input=OneShotInputParams(text=settings.prompt.greeting or "Hi, how can I help?"),
        selected_tools=[],
        medium={
            "serverWebSocket": {
                "inputSampleRate": 16000,
                "outputSampleRate": 48000,
                "clientBufferSizeMs": 80,
            }
        },
    )


def _instrumented_google_llm_service(base_cls, recorder: PipelineRecorder):
    class InstrumentedGoogleLLMService(base_cls):
        async def push_error(self, error_msg: str, exception: Exception | None = None, fatal: bool = False):
            await _push_llm_error_fallback(self, recorder, "gemini", error_msg)
            await super().push_error(error_msg, exception=exception, fatal=fatal)

        async def _stream_content(self, params):
            recorder.handle_llm_request_started({"source": "gemini"})
            response = await super()._stream_content(params)

            async def wrapped_response():
                async for chunk in response:
                    text = _first_text_from_gemini_chunk(chunk)
                    if text:
                        recorder.handle_llm_stream_chunk(text, {"source": "gemini_stream_chunk"})
                    yield chunk

            return wrapped_response()

    return InstrumentedGoogleLLMService


def _instrumented_openai_compatible_llm_service(base_cls, recorder: PipelineRecorder, *, provider: str):
    class InstrumentedOpenAICompatibleLLMService(base_cls):
        async def push_error(self, error_msg: str, exception: Exception | None = None, fatal: bool = False):
            await _push_llm_error_fallback(self, recorder, provider, error_msg)
            await super().push_error(error_msg, exception=exception, fatal=fatal)

        async def _stream_chat_completions_specific_context(self, context):
            recorder.handle_llm_request_started({"source": provider})
            stream = await super()._stream_chat_completions_specific_context(context)
            return _wrap_openai_stream(stream, recorder, provider)

        async def _stream_chat_completions_universal_context(self, context):
            recorder.handle_llm_request_started({"source": provider})
            stream = await super()._stream_chat_completions_universal_context(context)
            return _wrap_openai_stream(stream, recorder, provider)

    return InstrumentedOpenAICompatibleLLMService


async def _push_llm_error_fallback(processor: Any, recorder: PipelineRecorder, provider: str, error_msg: str) -> None:
    from pipecat.frames.frames import LLMTextFrame

    fallback_text = "Sorry, I am having trouble connecting right now."
    recorder.emit(
        "llm.provider_failed",
        provider=provider,
        metadata={
            "llm_provider": recorder.llm_provider,
            "llm_model": recorder.llm_model,
            "error_preview": str(error_msg)[:220],
            "fallback_spoken": True,
        },
        once_per_turn=True,
    )
    recorder.handle_llm_stream_chunk(
        fallback_text,
        {"source": "llm_error_fallback", "llm_provider": recorder.llm_provider, "llm_model": recorder.llm_model},
    )
    await processor.push_frame(LLMTextFrame(fallback_text))


def _instrumented_ultravox_service(base_cls, recorder: PipelineRecorder):
    class InstrumentedUltravoxService(base_cls):
        async def _receive_task_handler(self, websocket):
            recorder.handle_llm_request_started({"source": "ultravox"})
            return await super()._receive_task_handler(websocket)

    return InstrumentedUltravoxService


def _wrap_openai_stream(stream, recorder: PipelineRecorder, provider: str):
    async def wrapped_response():
        async for chunk in stream:
            text = _first_text_from_openai_chunk(chunk)
            if text:
                recorder.handle_llm_stream_chunk(text, {"source": f"{provider}_stream_chunk"})
            yield chunk

    return wrapped_response()


def _build_mock_llm_service(response_text: str, recorder: PipelineRecorder):
    from pipecat.frames.frames import LLMContextFrame, LLMFullResponseEndFrame, LLMFullResponseStartFrame, LLMMessagesFrame, LLMTextFrame
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    class MockLLMService(FrameProcessor):
        def __init__(self) -> None:
            super().__init__(name="MockLLMService")

        async def process_frame(self, frame, direction: FrameDirection):
            await super().process_frame(frame, direction)
            if isinstance(frame, (LLMContextFrame, LLMMessagesFrame)):
                recorder.handle_llm_request_started({"source": "mock"})
                recorder.handle_llm_stream_chunk(response_text, {"source": "mock_stream_chunk"})
                await self.push_frame(LLMFullResponseStartFrame(), direction)
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


def _first_text_from_openai_chunk(chunk) -> str | None:
    choices = getattr(chunk, "choices", None) or []
    if not choices:
        return None
    delta = getattr(choices[0], "delta", None)
    content = getattr(delta, "content", None) if delta else None
    return str(content) if content else None


def _cartesia_text_aggregation_mode(text_aggregation_mode_enum, configured: str):
    return getattr(text_aggregation_mode_enum, configured.upper(), text_aggregation_mode_enum.SENTENCE)


def _cartesia_service_with_buffer_delay(base_cls, max_buffer_delay_ms: int | None):
    if max_buffer_delay_ms is None:
        return base_cls
    buffer_delay = min(max(int(max_buffer_delay_ms), 0), 5000)

    class BufferedCartesiaTTSService(base_cls):
        def _build_msg(self, text: str = "", continue_transcript: bool = True, add_timestamps: bool = True, context_id: str = ""):
            payload = json.loads(super()._build_msg(text=text, continue_transcript=continue_transcript, add_timestamps=add_timestamps, context_id=context_id))
            payload["max_buffer_delay_ms"] = buffer_delay
            return json.dumps(payload)

    return BufferedCartesiaTTSService


def _register_transport_handlers(transport, recorder: PipelineRecorder, *, provider: str) -> None:
    if provider == "livekit":
        events = {
            "on_connected": "transport.connected",
            "on_disconnected": "transport.disconnected",
            "on_participant_connected": "client.joined",
            "on_participant_disconnected": "client.left",
            "on_audio_track_subscribed": "transport.audio_subscribed",
        }
    else:
        events = {
            "on_joined": "transport.connected",
            "on_left": "transport.disconnected",
            "on_error": "error",
            "on_first_participant_joined": "client.joined",
            "on_participant_joined": "client.joined",
            "on_participant_left": "client.left",
        }
    for event_name, output_name in events.items():
        try:
            @transport.event_handler(event_name)
            async def handler(_transport, *args, _output_name=output_name, _provider=provider):
                recorder.emit(
                    _output_name,
                    provider=_provider,
                    metadata={"args": [str(arg)[:160] for arg in args]},
                )
        except Exception:
            continue


def _register_tts_handlers(tts, recorder: PipelineRecorder) -> None:
    try:
        @tts.event_handler("on_tts_request")
        async def on_tts_request(_tts, context_id, text):
            recorder.handle_tts_request(str(context_id), str(text))
    except Exception:
        return


def _register_task_handlers(task, recorder: PipelineRecorder, greeting: str | None = None) -> None:
    @task.event_handler("on_pipeline_started")
    async def on_pipeline_started(_task, frame):
        recorder.emit("pipeline.started", metadata={"frame_type": frame.__class__.__name__})
        if greeting:
            asyncio.create_task(_queue_greeting(_task, recorder, greeting))

    @task.event_handler("on_pipeline_finished")
    async def on_pipeline_finished(_task, frame):
        recorder.emit("pipeline.finished", metadata={"frame_type": frame.__class__.__name__})


async def _queue_greeting(task, recorder: PipelineRecorder, greeting: str) -> None:
    try:
        from pipecat.frames.frames import TTSSpeakFrame

        await asyncio.sleep(0.25)
        await task.queue_frame(TTSSpeakFrame(greeting))
        recorder.emit("transcript.assistant", metadata={"text": greeting, "source": "greeting"})
    except Exception as exc:
        recorder.emit("error", metadata={"error_type": exc.__class__.__name__, "error_message": str(exc)[:240]})


def _frame_text(frame: Any) -> str:
    for attr in ("text", "transcript"):
        value = getattr(frame, attr, None)
        if value:
            return str(value)
    return ""


def _setup_provider_log_redaction() -> None:
    if getattr(_setup_provider_log_redaction, "_configured", False):
        return
    try:
        from loguru import logger as loguru_logger
    except Exception:
        return
    auth_pattern = re.compile(r"(Authorization['\"]?: ['\"](?:Bearer|Token) )[^'\"]+", re.IGNORECASE)

    def redacting_sink(message) -> None:
        sys.stderr.write(auth_pattern.sub(r"\1[redacted]", str(message)))

    loguru_logger.remove()
    loguru_logger.add(redacting_sink, level="INFO", colorize=True)
    setattr(_setup_provider_log_redaction, "_configured", True)
