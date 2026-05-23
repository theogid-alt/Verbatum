from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import os
from typing import Mapping


DEFAULT_SYSTEM_PROMPT = (
    "You are Alicia, a warm female voice agent created by CRTG AI for CRTG Real Estate. "
    "You only handle Dubai real estate. "
    "Never say you are an AI, LLM, model, bot, or unable to fulfill a request. "
    "Sound like a relaxed Dubai real estate concierge in her 20s, not a form or call-center script. "
    "Primary rule: do not push the caller through qualification questions. Conversation first, sales later. "
    "Never repeat, recap, mirror, validate, complete, or label the caller's words. "
    "Never say 'you're looking for', 'that's a great budget', 'sounds like', 'rent or purchase', "
    "'what's your budget', 'which area', or 'what property are we looking at'. "
    "Never invent personal experiences, your day, walks, Marina, or off-call life. "
    "No market praise, no luxury hype, no obvious Dubai filler, no rental-yield clichés. "
    "Avoid default questions like 'what's on your mind' or 'what kind of house are you looking for'. "
    "If the caller says chill, stop asking questions, let's talk, or similar, answer socially and ask no question. "
    "Example: 'Fair. I'm Alicia. We can keep it easy.' "
    "If they ask your name or how you are, answer directly and stay casual; do not pretend you went anywhere. "
    "Only ask a question when one exact detail is truly needed right now; otherwise offer WhatsApp follow-up. "
    "Prefer helpful statements: 'I can send a few options on WhatsApp.' 'We can figure that out later.' "
    "'No rush, we can keep it broad.' "
    "Never end the call, say you have to go, say call me back later, or close the conversation unless the caller "
    "clearly says goodbye. If the caller sounds done, offer WhatsApp follow-up and stop probing. "
    "Use at most one casual filler every few replies: Yeah, Okay so, Alright, One sec, Hold on one second. "
    "Usually answer in 4 to 10 words. Use two short sentences only for direct factual questions."
)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _env(env: Mapping[str, str], key: str, default: str | None = None) -> str | None:
    return _clean(env.get(key)) or default


def _env_bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    value = _clean(env.get(key))
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _env_int(env: Mapping[str, str], key: str, default: int | None = None) -> int | None:
    value = _clean(env.get(key))
    if value is None:
        return default
    return int(value)


def _env_float(
    env: Mapping[str, str],
    key: str,
    default: float | None = None,
) -> float | None:
    value = _clean(env.get(key))
    if value is None:
        return default
    return float(value)


def _deepgram_utterance_end_ms(env: Mapping[str, str]) -> int | None:
    value = _env_int(env, "VERBATIM_DEEPGRAM_UTTERANCE_END_MS", 1000)
    if value is None:
        return None
    return max(value, 1000)


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env_file(path: str | Path = ".env", *, override: bool = False) -> None:
    """Load a small dotenv-compatible file without requiring python-dotenv at import time."""
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        existing = os.environ.get(key)
        if not override and existing is not None and existing.strip():
            continue
        os.environ[key] = _strip_quotes(value.strip())


@dataclass(frozen=True)
class AgentConfig:
    agent_id: str = "agent_demo"
    client_id: str = "internal"
    environment: str = "development"
    log_level: str = "debug"


@dataclass(frozen=True)
class ProviderConfig:
    transport_provider: str = "daily"
    daily_api_key: str | None = None
    daily_room_url: str | None = None
    daily_room_token: str | None = None
    daily_geo: str | None = None
    daily_force_create_room: bool = False
    livekit_url: str | None = None
    livekit_api_url: str | None = None
    livekit_api_key: str | None = None
    livekit_api_secret: str | None = None
    livekit_room_name: str | None = None
    livekit_empty_timeout_seconds: int = 600
    livekit_max_participants: int = 4
    livekit_token_ttl_seconds: int = 3600
    livekit_audio_in_sample_rate: int | None = None
    livekit_audio_out_sample_rate: int | None = None
    livekit_audio_out_bitrate: int = 96000
    livekit_audio_out_10ms_chunks: int = 4
    livekit_audio_out_auto_silence: bool = True
    livekit_browser_echo_cancellation: bool = True
    livekit_browser_noise_suppression: bool = True
    livekit_browser_auto_gain_control: bool = True
    livekit_browser_audio_sample_rate: int | None = 48000
    deepgram_api_key: str | None = None
    google_api_key: str | None = None
    openai_api_key: str | None = None
    groq_api_key: str | None = None
    qwen_api_key: str | None = None
    qwen_base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    xai_api_key: str | None = None
    xai_base_url: str = "https://api.x.ai/v1"
    ultravox_api_key: str | None = None
    hume_api_key: str | None = None
    hume_secret_key: str | None = None
    hume_evi_config_id: str | None = None
    hume_evi_config_version: int | None = None
    hume_evi_voice_id: str | None = None
    hume_evi_verbose_transcription: bool = True
    hume_evi_send_system_prompt: bool = True
    cartesia_api_key: str | None = None
    stt_provider: str = "deepgram"
    deepgram_model: str = "nova-3-general"
    deepgram_endpointing: int | bool | None = 100
    deepgram_utterance_end_ms: int | None = 1000
    deepgram_flux_eager_eot_threshold: float | None = 0.45
    deepgram_flux_eot_threshold: float | None = 0.75
    deepgram_flux_eot_timeout_ms: int | None = 1200
    deepgram_flux_min_confidence: float | None = None
    llm_provider: str = "gemini"
    gemini_model: str = "gemini-2.5-flash"
    openai_model: str = "gpt-4o-mini"
    groq_model: str = "llama-3.1-8b-instant"
    qwen_model: str = "qwen3.5-2b"
    xai_model: str = "grok-4-1-fast-non-reasoning"
    ultravox_model: str = "fixie-ai/ultravox"
    ultravox_voice_id: str | None = None
    ultravox_max_duration_seconds: int = 3600
    ultravox_turn_endpoint_delay_seconds: float | None = None
    ultravox_minimum_turn_duration_seconds: float | None = None
    ultravox_minimum_interruption_duration_seconds: float | None = None
    ultravox_frame_activation_threshold: float | None = None
    ultravox_client_buffer_size_ms: int | None = None
    ultravox_media_idle_timeout_seconds: float | None = None
    mock_llm_response: str = "Got it. I can help with that."

    @property
    def llm_model(self) -> str:
        if self.llm_provider == "openai":
            return self.openai_model
        if self.llm_provider == "groq":
            return self.groq_model
        if self.llm_provider == "qwen":
            return self.qwen_model
        if self.llm_provider == "xai":
            return self.xai_model
        if self.llm_provider == "ultravox":
            return self.ultravox_model
        if self.llm_provider == "mock":
            return "mock-immediate"
        return self.gemini_model


@dataclass(frozen=True)
class VoiceConfig:
    cartesia_voice_id: str | None
    cartesia_model: str = "sonic-3"
    tts_text_aggregation_mode: str = "sentence"
    tts_first_phrase_flush_enabled: bool = False
    tts_first_flush_timeout_ms: int = 150
    tts_first_flush_min_words: int = 2
    tts_first_flush_max_words: int = 6
    tts_after_first_mode: str = "sentence"
    cartesia_max_buffer_delay_ms: int | None = None


@dataclass(frozen=True)
class PromptConfig:
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    hume_evi_system_prompt: str | None = None
    greeting: str | None = None
    max_tokens: int = 32
    temperature: float = 0.0


@dataclass(frozen=True)
class InstrumentationConfig:
    enable_jsonl_events: bool = True
    event_log_path: Path = Path("./data/verbatim/events.jsonl")
    call_summary_dir: Path = Path("./data/verbatim/calls")
    transcript_dir: Path = Path("./data/verbatim/transcripts")
    slow_turn_trace_dir: Path = Path("./data/verbatim/slow_turns")
    enable_otel: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"


@dataclass(frozen=True)
class SessionConfig:
    bot_name: str = "Verbatim"
    room_ttl_seconds: int = 3600
    idle_timeout_seconds: int = 300
    user_turn_stop_timeout: float = 5.0
    llm_history_messages: int = 1
    latency_diagnostic_mode: bool = True
    final_transcript_eager_commit: bool = True
    final_transcript_commit_delay_ms: int = 0
    final_transcript_require_complete_utterance: bool = False
    final_transcript_fragment_delay_ms: int = 220
    response_style_guard_enabled: bool = True
    vad_only_user_turn_start: bool = True
    mute_user_while_bot_speaking: bool = False
    llm_prewarm_enabled: bool = True
    echo_suppression_ms: int = 0
    fast_ack_enabled: bool = False
    fast_ack_timeout_ms: int = 350
    fast_ack_text: str = "Sure."
    assistant_min_speak_ms_before_barge_in: int = 400
    barge_in_min_speech_ms: int = 300
    barge_in_min_transcript_words: int = 2
    hard_interrupt_phrases: str = "stop,wait,hold on,let me finish,actually,no"
    utterance_split_window_ms: int = 1200
    user_resume_after_assistant_window_ms: int = 800


@dataclass(frozen=True)
class Settings:
    agent: AgentConfig
    providers: ProviderConfig
    voice: VoiceConfig
    prompt: PromptConfig
    instrumentation: InstrumentationConfig
    session: SessionConfig

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        source = env if env is not None else os.environ
        endpointing = _env(source, "VERBATIM_DEEPGRAM_ENDPOINTING", "100")
        endpointing_value: int | bool | None
        if endpointing and endpointing.lower() == "false":
            endpointing_value = False
        elif endpointing:
            endpointing_value = int(endpointing)
        else:
            endpointing_value = None
        final_commit_delay_ms = _env_int(
            source, "VERBATIM_FINAL_TRANSCRIPT_COMMIT_DELAY_MS", 0
        )
        final_fragment_delay_ms = _env_int(
            source, "VERBATIM_FINAL_TRANSCRIPT_FRAGMENT_DELAY_MS", 220
        )

        return cls(
            agent=AgentConfig(
                agent_id=_env(source, "VERBATIM_AGENT_ID", "agent_demo") or "agent_demo",
                client_id=_env(source, "VERBATIM_CLIENT_ID", "internal") or "internal",
                environment=_env(source, "VERBATIM_ENV", "development") or "development",
                log_level=_env(source, "VERBATIM_LOG_LEVEL", "debug") or "debug",
            ),
            providers=ProviderConfig(
                transport_provider=(
                    _env(source, "VERBATIM_TRANSPORT_PROVIDER", "daily") or "daily"
                ).lower(),
                daily_api_key=_env(source, "DAILY_API_KEY"),
                daily_room_url=_env(source, "DAILY_ROOM_URL"),
                daily_room_token=_env(source, "DAILY_ROOM_TOKEN"),
                daily_geo=_env(source, "DAILY_GEO"),
                daily_force_create_room=_env_bool(
                    source, "VERBATIM_DAILY_FORCE_CREATE_ROOM", False
                ),
                livekit_url=_env(source, "LIVEKIT_URL"),
                livekit_api_url=_env(source, "LIVEKIT_API_URL"),
                livekit_api_key=_env(source, "LIVEKIT_API_KEY"),
                livekit_api_secret=_env(source, "LIVEKIT_API_SECRET"),
                livekit_room_name=_env(source, "LIVEKIT_ROOM_NAME"),
                livekit_empty_timeout_seconds=_env_int(
                    source, "LIVEKIT_EMPTY_TIMEOUT_SECONDS", 600
                )
                or 600,
                livekit_max_participants=_env_int(source, "LIVEKIT_MAX_PARTICIPANTS", 4) or 4,
                livekit_token_ttl_seconds=_env_int(
                    source, "LIVEKIT_TOKEN_TTL_SECONDS", 3600
                )
                or 3600,
                livekit_audio_in_sample_rate=_env_int(
                    source, "VERBATIM_LIVEKIT_AUDIO_IN_SAMPLE_RATE", None
                ),
                livekit_audio_out_sample_rate=_env_int(
                    source, "VERBATIM_LIVEKIT_AUDIO_OUT_SAMPLE_RATE", None
                ),
                livekit_audio_out_bitrate=_env_int(
                    source, "VERBATIM_LIVEKIT_AUDIO_OUT_BITRATE", 96000
                )
                or 96000,
                livekit_audio_out_10ms_chunks=_env_int(
                    source, "VERBATIM_LIVEKIT_AUDIO_OUT_10MS_CHUNKS", 4
                )
                or 4,
                livekit_audio_out_auto_silence=_env_bool(
                    source, "VERBATIM_LIVEKIT_AUDIO_OUT_AUTO_SILENCE", True
                ),
                livekit_browser_echo_cancellation=_env_bool(
                    source, "VERBATIM_LIVEKIT_BROWSER_ECHO_CANCELLATION", True
                ),
                livekit_browser_noise_suppression=_env_bool(
                    source, "VERBATIM_LIVEKIT_BROWSER_NOISE_SUPPRESSION", True
                ),
                livekit_browser_auto_gain_control=_env_bool(
                    source, "VERBATIM_LIVEKIT_BROWSER_AUTO_GAIN_CONTROL", True
                ),
                livekit_browser_audio_sample_rate=_env_int(
                    source, "VERBATIM_LIVEKIT_BROWSER_AUDIO_SAMPLE_RATE", 48000
                ),
                deepgram_api_key=_env(source, "DEEPGRAM_API_KEY"),
                google_api_key=_env(source, "GOOGLE_API_KEY"),
                openai_api_key=_env(source, "OPENAI_API_KEY"),
                groq_api_key=_env(source, "GROQ_API_KEY"),
                qwen_api_key=_env(source, "QWEN_API_KEY") or _env(source, "DASHSCOPE_API_KEY"),
                qwen_base_url=(
                    _env(
                        source,
                        "QWEN_BASE_URL",
                        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                    )
                    or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
                ),
                xai_api_key=_env(source, "XAI_API_KEY"),
                xai_base_url=_env(source, "XAI_BASE_URL", "https://api.x.ai/v1")
                or "https://api.x.ai/v1",
                ultravox_api_key=_env(source, "ULTRAVOX_API_KEY"),
                hume_api_key=_env(source, "HUME_API_KEY"),
                hume_secret_key=_env(source, "HUME_SECRET_KEY"),
                hume_evi_config_id=_env(source, "HUME_EVI_CONFIG_ID"),
                hume_evi_config_version=_env_int(source, "HUME_EVI_CONFIG_VERSION", None),
                hume_evi_voice_id=_env(source, "HUME_EVI_VOICE_ID"),
                hume_evi_verbose_transcription=_env_bool(
                    source, "HUME_EVI_VERBOSE_TRANSCRIPTION", True
                ),
                hume_evi_send_system_prompt=_env_bool(
                    source, "HUME_EVI_SEND_SYSTEM_PROMPT", True
                ),
                cartesia_api_key=_env(source, "CARTESIA_API_KEY"),
                stt_provider=(
                    _env(source, "VERBATIM_STT_PROVIDER", "deepgram")
                    or "deepgram"
                ).lower(),
                deepgram_model=_env(source, "VERBATIM_DEEPGRAM_MODEL", "nova-3-general")
                or "nova-3-general",
                deepgram_endpointing=endpointing_value,
                deepgram_utterance_end_ms=_deepgram_utterance_end_ms(source),
                deepgram_flux_eager_eot_threshold=_env_float(
                    source, "VERBATIM_DEEPGRAM_FLUX_EAGER_EOT_THRESHOLD", 0.45
                ),
                deepgram_flux_eot_threshold=_env_float(
                    source, "VERBATIM_DEEPGRAM_FLUX_EOT_THRESHOLD", 0.75
                ),
                deepgram_flux_eot_timeout_ms=_env_int(
                    source, "VERBATIM_DEEPGRAM_FLUX_EOT_TIMEOUT_MS", 1200
                ),
                deepgram_flux_min_confidence=_env_float(
                    source, "VERBATIM_DEEPGRAM_FLUX_MIN_CONFIDENCE", None
                ),
                llm_provider=(
                    _env(source, "VERBATIM_LLM_PROVIDER", "gemini") or "gemini"
                ).lower(),
                gemini_model=_env(source, "VERBATIM_GEMINI_MODEL", "gemini-2.5-flash")
                or "gemini-2.5-flash",
                openai_model=_env(source, "VERBATIM_OPENAI_MODEL", "gpt-4o-mini")
                or "gpt-4o-mini",
                groq_model=_env(source, "VERBATIM_GROQ_MODEL", "llama-3.1-8b-instant")
                or "llama-3.1-8b-instant",
                qwen_model=_env(source, "VERBATIM_QWEN_MODEL", "qwen3.5-2b")
                or "qwen3.5-2b",
                xai_model=_env(
                    source,
                    "VERBATIM_XAI_MODEL",
                    "grok-4-1-fast-non-reasoning",
                )
                or "grok-4-1-fast-non-reasoning",
                ultravox_model=_env(source, "VERBATIM_ULTRAVOX_MODEL", "fixie-ai/ultravox")
                or "fixie-ai/ultravox",
                ultravox_voice_id=_env(source, "VERBATIM_ULTRAVOX_VOICE_ID"),
                ultravox_max_duration_seconds=_env_int(
                    source, "VERBATIM_ULTRAVOX_MAX_DURATION_SECONDS", 3600
                )
                or 3600,
                ultravox_turn_endpoint_delay_seconds=_env_float(
                    source, "VERBATIM_ULTRAVOX_TURN_ENDPOINT_DELAY_SECONDS", None
                ),
                ultravox_minimum_turn_duration_seconds=_env_float(
                    source, "VERBATIM_ULTRAVOX_MINIMUM_TURN_DURATION_SECONDS", None
                ),
                ultravox_minimum_interruption_duration_seconds=_env_float(
                    source,
                    "VERBATIM_ULTRAVOX_MINIMUM_INTERRUPTION_DURATION_SECONDS",
                    None,
                ),
                ultravox_frame_activation_threshold=_env_float(
                    source, "VERBATIM_ULTRAVOX_FRAME_ACTIVATION_THRESHOLD", None
                ),
                ultravox_client_buffer_size_ms=_env_int(
                    source, "VERBATIM_ULTRAVOX_CLIENT_BUFFER_SIZE_MS", None
                ),
                ultravox_media_idle_timeout_seconds=_env_float(
                    source, "VERBATIM_ULTRAVOX_MEDIA_IDLE_TIMEOUT_SECONDS", None
                ),
                mock_llm_response=_env(
                    source,
                    "VERBATIM_MOCK_LLM_RESPONSE",
                    "Got it. I can help with that.",
                )
                or "Got it. I can help with that.",
            ),
            voice=VoiceConfig(
                cartesia_voice_id=_env(source, "VERBATIM_CARTESIA_VOICE_ID"),
                cartesia_model=_env(source, "VERBATIM_CARTESIA_MODEL", "sonic-3") or "sonic-3",
                tts_text_aggregation_mode=(
                    _env(source, "VERBATIM_TTS_TEXT_AGGREGATION_MODE", "sentence")
                    or "sentence"
                ).lower(),
                tts_first_phrase_flush_enabled=_env_bool(
                    source, "VERBATIM_TTS_FIRST_PHRASE_FLUSH_ENABLED", False
                ),
                tts_first_flush_timeout_ms=_env_int(
                    source, "VERBATIM_TTS_FIRST_FLUSH_TIMEOUT_MS", 150
                )
                or 150,
                tts_first_flush_min_words=_env_int(
                    source, "VERBATIM_TTS_FIRST_FLUSH_MIN_WORDS", 2
                )
                or 2,
                tts_first_flush_max_words=_env_int(
                    source, "VERBATIM_TTS_FIRST_FLUSH_MAX_WORDS", 6
                )
                or 6,
                tts_after_first_mode=(
                    _env(source, "VERBATIM_TTS_AFTER_FIRST_MODE", "sentence") or "sentence"
                ).lower(),
                cartesia_max_buffer_delay_ms=_env_int(
                    source, "VERBATIM_CARTESIA_MAX_BUFFER_DELAY_MS", None
                ),
            ),
            prompt=PromptConfig(
                system_prompt=_env(source, "VERBATIM_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)
                or DEFAULT_SYSTEM_PROMPT,
                hume_evi_system_prompt=_env(source, "HUME_EVI_SYSTEM_PROMPT"),
                greeting=_env(source, "VERBATIM_GREETING"),
                max_tokens=_env_int(source, "VERBATIM_LLM_MAX_TOKENS", 32) or 32,
                temperature=_env_float(source, "VERBATIM_LLM_TEMPERATURE", 0.0) or 0.0,
            ),
            instrumentation=InstrumentationConfig(
                enable_jsonl_events=_env_bool(source, "VERBATIM_ENABLE_JSONL_EVENTS", True),
                event_log_path=Path(
                    _env(source, "VERBATIM_EVENT_LOG_PATH", "./data/verbatim/events.jsonl")
                    or "./data/verbatim/events.jsonl"
                ),
                call_summary_dir=Path(
                    _env(source, "VERBATIM_CALL_SUMMARY_DIR", "./data/verbatim/calls")
                    or "./data/verbatim/calls"
                ),
                transcript_dir=Path(
                    _env(source, "VERBATIM_TRANSCRIPT_DIR", "./data/verbatim/transcripts")
                    or "./data/verbatim/transcripts"
                ),
                slow_turn_trace_dir=Path(
                    _env(source, "VERBATIM_SLOW_TURN_TRACE_DIR", "./data/verbatim/slow_turns")
                    or "./data/verbatim/slow_turns"
                ),
                enable_otel=_env_bool(source, "VERBATIM_ENABLE_OTEL", False),
                otel_exporter_otlp_endpoint=_env(
                    source,
                    "VERBATIM_OTEL_EXPORTER_OTLP_ENDPOINT",
                    "http://localhost:4317",
                )
                or "http://localhost:4317",
            ),
            session=SessionConfig(
                bot_name=_env(source, "VERBATIM_BOT_NAME", "Verbatim") or "Verbatim",
                room_ttl_seconds=_env_int(source, "VERBATIM_ROOM_TTL_SECONDS", 3600) or 3600,
                idle_timeout_seconds=_env_int(source, "VERBATIM_IDLE_TIMEOUT_SECONDS", 300)
                or 300,
                user_turn_stop_timeout=_env_float(
                    source, "VERBATIM_USER_TURN_STOP_TIMEOUT", 5.0
                )
                or 5.0,
                llm_history_messages=_env_int(source, "VERBATIM_LLM_HISTORY_MESSAGES", 1)
                or 1,
                latency_diagnostic_mode=_env_bool(
                    source, "VERBATIM_LATENCY_DIAGNOSTIC_MODE", True
                ),
                final_transcript_eager_commit=_env_bool(
                    source, "VERBATIM_FINAL_TRANSCRIPT_EAGER_COMMIT", True
                ),
                final_transcript_commit_delay_ms=max(
                    0,
                    0 if final_commit_delay_ms is None else final_commit_delay_ms,
                ),
                final_transcript_require_complete_utterance=_env_bool(
                    source, "VERBATIM_FINAL_TRANSCRIPT_REQUIRE_COMPLETE_UTTERANCE", False
                ),
                final_transcript_fragment_delay_ms=max(
                    0,
                    220 if final_fragment_delay_ms is None else final_fragment_delay_ms,
                ),
                response_style_guard_enabled=_env_bool(
                    source, "VERBATIM_RESPONSE_STYLE_GUARD_ENABLED", True
                ),
                vad_only_user_turn_start=_env_bool(
                    source, "VERBATIM_VAD_ONLY_USER_TURN_START", True
                ),
                mute_user_while_bot_speaking=_env_bool(
                    source, "VERBATIM_MUTE_USER_WHILE_BOT_SPEAKING", False
                ),
                llm_prewarm_enabled=_env_bool(source, "VERBATIM_LLM_PREWARM", True),
                echo_suppression_ms=_env_int(source, "VERBATIM_ECHO_SUPPRESSION_MS", 0)
                or 0,
                fast_ack_enabled=_env_bool(source, "VERBATIM_FAST_ACK_ENABLED", False),
                fast_ack_timeout_ms=_env_int(source, "VERBATIM_FAST_ACK_TIMEOUT_MS", 350)
                or 350,
                fast_ack_text=_env(source, "VERBATIM_FAST_ACK_TEXT", "Sure.") or "Sure.",
                assistant_min_speak_ms_before_barge_in=_env_int(
                    source,
                    "VERBATIM_ASSISTANT_MIN_SPEAK_MS_BEFORE_BARGE_IN",
                    400,
                )
                or 400,
                barge_in_min_speech_ms=_env_int(
                    source,
                    "VERBATIM_BARGE_IN_MIN_SPEECH_MS",
                    300,
                )
                or 300,
                barge_in_min_transcript_words=_env_int(
                    source,
                    "VERBATIM_BARGE_IN_MIN_TRANSCRIPT_WORDS",
                    2,
                )
                or 2,
                hard_interrupt_phrases=_env(
                    source,
                    "VERBATIM_HARD_INTERRUPT_PHRASES",
                    "stop,wait,hold on,let me finish,actually,no",
                )
                or "stop,wait,hold on,let me finish,actually,no",
                utterance_split_window_ms=_env_int(
                    source,
                    "VERBATIM_UTTERANCE_SPLIT_WINDOW_MS",
                    1200,
                )
                or 1200,
                user_resume_after_assistant_window_ms=_env_int(
                    source,
                    "VERBATIM_USER_RESUME_AFTER_ASSISTANT_WINDOW_MS",
                    800,
                )
                or 800,
            ),
        )

    def missing_room_keys(self, transport_provider: str | None = None) -> list[str]:
        provider = (transport_provider or self.providers.transport_provider or "daily").lower()
        if (
            provider == "daily"
            and self.providers.daily_room_url
            and not self.providers.daily_geo
            and not self.providers.daily_force_create_room
        ):
            return []
        if provider == "daily":
            return [] if self.providers.daily_api_key else ["DAILY_API_KEY"]
        if provider == "livekit":
            required = {
                "LIVEKIT_URL": self.providers.livekit_url,
                "LIVEKIT_API_KEY": self.providers.livekit_api_key,
                "LIVEKIT_API_SECRET": self.providers.livekit_api_secret,
            }
            return [key for key, value in required.items() if not value]
        return ["VERBATIM_TRANSPORT_PROVIDER"]

    def missing_agent_keys(self) -> list[str]:
        missing: list[str] = []
        transport_provider = self.providers.transport_provider
        if transport_provider == "daily":
            required_transport = {"DAILY_API_KEY": self.providers.daily_api_key}
        elif transport_provider == "livekit":
            required_transport = {
                "LIVEKIT_URL": self.providers.livekit_url,
                "LIVEKIT_API_KEY": self.providers.livekit_api_key,
                "LIVEKIT_API_SECRET": self.providers.livekit_api_secret,
            }
        else:
            required_transport = {"VERBATIM_TRANSPORT_PROVIDER": None}
        if self.providers.llm_provider == "ultravox":
            required = {
                **required_transport,
                "ULTRAVOX_API_KEY": self.providers.ultravox_api_key,
            }
            return [key for key, value in required.items() if not value]
        required = {
            **required_transport,
            "DEEPGRAM_API_KEY": self.providers.deepgram_api_key,
            "CARTESIA_API_KEY": self.providers.cartesia_api_key,
            "VERBATIM_CARTESIA_VOICE_ID": self.voice.cartesia_voice_id,
        }
        for key, value in required.items():
            if not value:
                missing.append(key)
        llm_provider = self.providers.llm_provider
        if llm_provider == "gemini" and not self.providers.google_api_key:
            missing.append("GOOGLE_API_KEY")
        elif llm_provider == "openai" and not self.providers.openai_api_key:
            missing.append("OPENAI_API_KEY")
        elif llm_provider == "groq" and not self.providers.groq_api_key:
            missing.append("GROQ_API_KEY")
        elif llm_provider == "qwen" and not self.providers.qwen_api_key:
            missing.append("QWEN_API_KEY")
        elif llm_provider == "xai" and not self.providers.xai_api_key:
            missing.append("XAI_API_KEY")
        elif llm_provider == "ultravox" and not self.providers.ultravox_api_key:
            missing.append("ULTRAVOX_API_KEY")
        elif llm_provider not in {"gemini", "openai", "groq", "qwen", "xai", "ultravox", "mock"}:
            missing.append("VERBATIM_LLM_PROVIDER")
        return missing


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_env_file()
    return Settings.from_env()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
