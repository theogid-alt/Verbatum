from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
import os
from pathlib import Path
from typing import Any, Mapping


DEFAULT_SYSTEM_PROMPT = (
    "You are a sharp real estate voice assistant. "
    "Answer the caller's actual question first. "
    "Do not guess, assume, or pre-fill the caller's request before they say it. "
    "Do not block simple questions behind qualification questions. "
    "If they ask for price, answer or say you can send it by SMS. "
    "After discussing a specific property, gently offer to book a property viewing. "
    "After a viewing is booked, offer to send an SMS confirmation. "
    "Never say a booking, calendar check, deletion, or SMS succeeded unless the tool result confirmed it. "
    "Ask at most one useful follow-up question. "
    "Do not repeat or rephrase what the caller said. "
    "Avoid form-like questions unless the caller asks for recommendations. "
    "Keep replies very short, usually 4-14 words, max two short sentences. "
    "Do not claim a company, city, or name unless provided."
)

DEFAULT_HUME_SYSTEM_PROMPT = (
    "You are a friendly real estate voice assistant. "
    "Stay focused on property questions, prices, listings, viewings, availability, and next steps. "
    "Keep replies short: one or two spoken sentences. "
    "Do not start every answer with okay. Vary naturally, and often answer directly. "
    "Do not interrupt. Wait until the caller finishes. "
    "Answer the question first. If details are missing, say so briefly and offer SMS follow-up. "
    "After discussing a specific property, gently offer to book a property viewing. "
    "After a viewing is booked, offer to send an SMS confirmation. "
    "Do not force qualification questions or drift into unrelated topics. "
    "Do not claim a company, city, or name unless provided."
)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env_file(path: str | Path = ".env", *, override: bool = False) -> None:
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
        if not override and os.environ.get(key):
            continue
        os.environ[key] = _strip_quotes(value.strip())


def _env(source: Mapping[str, str], key: str, default: str | None = None) -> str | None:
    return _clean(source.get(key)) or default


def _env_bool(source: Mapping[str, str], key: str, default: bool) -> bool:
    value = _clean(source.get(key))
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _env_int(source: Mapping[str, str], key: str, default: int | None = None) -> int | None:
    value = _clean(source.get(key))
    return default if value is None else int(value)


def _env_float(source: Mapping[str, str], key: str, default: float | None = None) -> float | None:
    value = _clean(source.get(key))
    return default if value is None else float(value)


@dataclass(frozen=True)
class AgentConfig:
    agent_id: str = "agent_demo"
    client_id: str = "internal"
    environment: str = "development"
    log_level: str = "debug"


@dataclass(frozen=True)
class ProviderConfig:
    transport_provider: str = "livekit"
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
    hume_evi_use_config: bool = False
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
    llm_provider: str = "groq"
    gemini_model: str = "gemini-2.5-flash"
    openai_model: str = "gpt-4o-mini"
    groq_model: str = "llama-3.1-8b-instant"
    qwen_model: str = "qwen3.5-2b"
    xai_model: str = "grok-4-1-fast-non-reasoning"
    ultravox_model: str = "fixie-ai/ultravox"
    ultravox_voice_id: str | None = None
    ultravox_max_duration_seconds: int = 3600
    mock_llm_response: str = "Got it. I can help with that."

    @property
    def llm_model(self) -> str:
        return {
            "gemini": self.gemini_model,
            "openai": self.openai_model,
            "groq": self.groq_model,
            "qwen": self.qwen_model,
            "xai": self.xai_model,
            "ultravox": self.ultravox_model,
            "mock": "mock-immediate",
            "hume_evi": "hume-evi",
        }.get(self.llm_provider, self.groq_model)


@dataclass(frozen=True)
class VoiceConfig:
    cartesia_voice_id: str | None = None
    cartesia_model: str = "sonic-3"
    tts_text_aggregation_mode: str = "sentence"
    cartesia_max_buffer_delay_ms: int | None = None


@dataclass(frozen=True)
class PromptConfig:
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    hume_evi_system_prompt: str | None = None
    greeting: str | None = "Hi, how can I help?"
    max_tokens: int = 32
    temperature: float = 0.0


@dataclass(frozen=True)
class InstrumentationConfig:
    enable_jsonl_events: bool = True
    event_log_path: Path = Path("./data/verbatim/events_v2_clean.jsonl")
    call_summary_dir: Path = Path("./data/verbatim/calls_v2_clean")
    transcript_dir: Path = Path("./data/verbatim/transcripts_v2_clean")


@dataclass(frozen=True)
class IntegrationConfig:
    nango_secret_key: str | None = None
    nango_api_base_url: str = "https://api.nango.dev"
    nango_google_calendar_integration_id: str = "google-calendar"
    nango_calendly_integration_id: str = "calendly"
    nango_salesforce_integration_id: str = "salesforce"
    nango_hubspot_integration_id: str = "hubspot"
    nango_pipedrive_integration_id: str = "pipedrive"
    nango_slack_integration_id: str = "slack"
    nango_gmail_integration_id: str = "gmail"
    nango_outlook_calendar_integration_id: str = "outlook"
    nango_google_sheets_integration_id: str = "google-sheets"
    nango_airtable_integration_id: str = "airtable"
    nango_notion_integration_id: str = "notion"
    nango_stripe_integration_id: str = "stripe"
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from_number: str | None = None
    twilio_messaging_service_sid: str | None = None
    twilio_whatsapp_from: str | None = None
    make_webhook_url: str | None = None
    zapier_webhook_url: str | None = None
    n8n_webhook_url: str | None = None
    generic_webhook_url: str | None = None
    zenchef_api_key: str | None = None
    thefork_api_key: str | None = None
    whatsapp_business_access_token: str | None = None
    whatsapp_business_phone_number_id: str | None = None
    stripe_api_key: str | None = None
    resend_api_key: str | None = None
    resend_from_email: str | None = None
    default_followup_phone: str | None = None
    default_followup_email: str | None = None
    followup_sms_default_body: str = "Thanks for calling. I will send the property details here shortly."
    followup_email_default_subject: str = "Your property follow-up"
    followup_email_default_body: str = "Thanks for calling. I will send the property details here shortly."
    default_client_id: str = "demo"
    tools_enabled: bool = True
    tool_timeout_ms: int = 2500
    integrations_db_path: Path = Path("./data/verbatim/integrations_v2.db")


@dataclass(frozen=True)
class SessionConfig:
    bot_name: str = "Verbatim"
    room_ttl_seconds: int = 3600
    idle_timeout_seconds: int = 300
    user_turn_stop_timeout: float = 5.0
    llm_history_messages: int = 1


@dataclass(frozen=True)
class Settings:
    agent: AgentConfig
    providers: ProviderConfig
    voice: VoiceConfig
    prompt: PromptConfig
    instrumentation: InstrumentationConfig
    integrations: IntegrationConfig
    session: SessionConfig

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        source = env if env is not None else os.environ
        endpointing = _env(source, "VERBATIM_DEEPGRAM_ENDPOINTING", "100")
        if endpointing and endpointing.lower() == "false":
            endpointing_value: int | bool | None = False
        elif endpointing:
            endpointing_value = int(endpointing)
        else:
            endpointing_value = None

        return cls(
            agent=AgentConfig(
                agent_id=_env(source, "VERBATIM_AGENT_ID", "agent_demo") or "agent_demo",
                client_id=_env(source, "VERBATIM_CLIENT_ID", "internal") or "internal",
                environment=_env(source, "VERBATIM_ENV", "development") or "development",
                log_level=_env(source, "VERBATIM_LOG_LEVEL", "debug") or "debug",
            ),
            providers=ProviderConfig(
                transport_provider=(_env(source, "VERBATIM_TRANSPORT_PROVIDER", "livekit") or "livekit").lower(),
                daily_api_key=_env(source, "DAILY_API_KEY"),
                daily_room_url=_env(source, "DAILY_ROOM_URL"),
                daily_room_token=_env(source, "DAILY_ROOM_TOKEN"),
                daily_geo=_env(source, "DAILY_GEO"),
                daily_force_create_room=_env_bool(source, "VERBATIM_DAILY_FORCE_CREATE_ROOM", False),
                livekit_url=_env(source, "LIVEKIT_URL"),
                livekit_api_url=_env(source, "LIVEKIT_API_URL"),
                livekit_api_key=_env(source, "LIVEKIT_API_KEY"),
                livekit_api_secret=_env(source, "LIVEKIT_API_SECRET"),
                livekit_room_name=_env(source, "LIVEKIT_ROOM_NAME"),
                livekit_empty_timeout_seconds=_env_int(source, "LIVEKIT_EMPTY_TIMEOUT_SECONDS", 600) or 600,
                livekit_max_participants=_env_int(source, "LIVEKIT_MAX_PARTICIPANTS", 4) or 4,
                livekit_token_ttl_seconds=_env_int(source, "LIVEKIT_TOKEN_TTL_SECONDS", 3600) or 3600,
                livekit_audio_in_sample_rate=_env_int(source, "VERBATIM_LIVEKIT_AUDIO_IN_SAMPLE_RATE"),
                livekit_audio_out_sample_rate=_env_int(source, "VERBATIM_LIVEKIT_AUDIO_OUT_SAMPLE_RATE"),
                livekit_audio_out_bitrate=_env_int(source, "VERBATIM_LIVEKIT_AUDIO_OUT_BITRATE", 96000) or 96000,
                livekit_audio_out_10ms_chunks=_env_int(source, "VERBATIM_LIVEKIT_AUDIO_OUT_10MS_CHUNKS", 4) or 4,
                livekit_audio_out_auto_silence=_env_bool(source, "VERBATIM_LIVEKIT_AUDIO_OUT_AUTO_SILENCE", True),
                deepgram_api_key=_env(source, "DEEPGRAM_API_KEY"),
                google_api_key=_env(source, "GOOGLE_API_KEY"),
                openai_api_key=_env(source, "OPENAI_API_KEY"),
                groq_api_key=_env(source, "GROQ_API_KEY"),
                qwen_api_key=_env(source, "QWEN_API_KEY") or _env(source, "DASHSCOPE_API_KEY"),
                qwen_base_url=_env(source, "QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
                or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                xai_api_key=_env(source, "XAI_API_KEY"),
                xai_base_url=_env(source, "XAI_BASE_URL", "https://api.x.ai/v1") or "https://api.x.ai/v1",
                ultravox_api_key=_env(source, "ULTRAVOX_API_KEY"),
                hume_api_key=_env(source, "HUME_API_KEY"),
                hume_secret_key=_env(source, "HUME_SECRET_KEY"),
                hume_evi_config_id=_env(source, "HUME_EVI_CONFIG_ID"),
                hume_evi_config_version=_env_int(source, "HUME_EVI_CONFIG_VERSION"),
                hume_evi_use_config=_env_bool(source, "HUME_EVI_USE_CONFIG", False),
                hume_evi_voice_id=_env(source, "HUME_EVI_VOICE_ID"),
                hume_evi_verbose_transcription=_env_bool(source, "HUME_EVI_VERBOSE_TRANSCRIPTION", True),
                hume_evi_send_system_prompt=_env_bool(source, "HUME_EVI_SEND_SYSTEM_PROMPT", True),
                cartesia_api_key=_env(source, "CARTESIA_API_KEY"),
                stt_provider=(_env(source, "VERBATIM_STT_PROVIDER", "deepgram") or "deepgram").lower(),
                deepgram_model=_env(source, "VERBATIM_DEEPGRAM_MODEL", "nova-3-general") or "nova-3-general",
                deepgram_endpointing=endpointing_value,
                deepgram_utterance_end_ms=_env_int(source, "VERBATIM_DEEPGRAM_UTTERANCE_END_MS", 1000),
                deepgram_flux_eager_eot_threshold=_env_float(source, "VERBATIM_DEEPGRAM_FLUX_EAGER_EOT_THRESHOLD", 0.45),
                deepgram_flux_eot_threshold=_env_float(source, "VERBATIM_DEEPGRAM_FLUX_EOT_THRESHOLD", 0.75),
                deepgram_flux_eot_timeout_ms=_env_int(source, "VERBATIM_DEEPGRAM_FLUX_EOT_TIMEOUT_MS", 1200),
                deepgram_flux_min_confidence=_env_float(source, "VERBATIM_DEEPGRAM_FLUX_MIN_CONFIDENCE"),
                llm_provider=(_env(source, "VERBATIM_LLM_PROVIDER", "groq") or "groq").lower(),
                gemini_model=_env(source, "VERBATIM_GEMINI_MODEL", "gemini-2.5-flash") or "gemini-2.5-flash",
                openai_model=_env(source, "VERBATIM_OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini",
                groq_model=_env(source, "VERBATIM_GROQ_MODEL", "llama-3.1-8b-instant") or "llama-3.1-8b-instant",
                qwen_model=_env(source, "VERBATIM_QWEN_MODEL", "qwen3.5-2b") or "qwen3.5-2b",
                xai_model=_env(source, "VERBATIM_XAI_MODEL", "grok-4-1-fast-non-reasoning")
                or "grok-4-1-fast-non-reasoning",
                ultravox_model=_env(source, "VERBATIM_ULTRAVOX_MODEL", "fixie-ai/ultravox") or "fixie-ai/ultravox",
                ultravox_voice_id=_env(source, "VERBATIM_ULTRAVOX_VOICE_ID"),
                ultravox_max_duration_seconds=_env_int(source, "VERBATIM_ULTRAVOX_MAX_DURATION_SECONDS", 3600) or 3600,
                mock_llm_response=_env(source, "VERBATIM_MOCK_LLM_RESPONSE", "Got it. I can help with that.")
                or "Got it. I can help with that.",
            ),
            voice=VoiceConfig(
                cartesia_voice_id=_env(source, "VERBATIM_CARTESIA_VOICE_ID"),
                cartesia_model=_env(source, "VERBATIM_CARTESIA_MODEL", "sonic-3") or "sonic-3",
                tts_text_aggregation_mode=(_env(source, "VERBATIM_TTS_TEXT_AGGREGATION_MODE", "sentence") or "sentence").lower(),
                cartesia_max_buffer_delay_ms=_env_int(source, "VERBATIM_CARTESIA_MAX_BUFFER_DELAY_MS"),
            ),
            prompt=PromptConfig(
                system_prompt=_env(source, "VERBATIM_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT) or DEFAULT_SYSTEM_PROMPT,
                hume_evi_system_prompt=_env(source, "HUME_EVI_SYSTEM_PROMPT", DEFAULT_HUME_SYSTEM_PROMPT),
                greeting=_env(source, "VERBATIM_GREETING", "Hi, how can I help?"),
                max_tokens=_env_int(source, "VERBATIM_LLM_MAX_TOKENS", 32) or 32,
                temperature=_env_float(source, "VERBATIM_LLM_TEMPERATURE", 0.0) or 0.0,
            ),
            instrumentation=InstrumentationConfig(
                enable_jsonl_events=_env_bool(source, "VERBATIM_ENABLE_JSONL_EVENTS", True),
                event_log_path=Path(_env(source, "VERBATIM_EVENT_LOG_PATH", "./data/verbatim/events_v2_clean.jsonl") or "./data/verbatim/events_v2_clean.jsonl"),
                call_summary_dir=Path(_env(source, "VERBATIM_CALL_SUMMARY_DIR", "./data/verbatim/calls_v2_clean") or "./data/verbatim/calls_v2_clean"),
                transcript_dir=Path(_env(source, "VERBATIM_TRANSCRIPT_DIR", "./data/verbatim/transcripts_v2_clean") or "./data/verbatim/transcripts_v2_clean"),
            ),
            integrations=IntegrationConfig(
                nango_secret_key=_env(source, "NANGO_SECRET_KEY"),
                nango_api_base_url=_env(source, "NANGO_API_BASE_URL", "https://api.nango.dev")
                or "https://api.nango.dev",
                nango_google_calendar_integration_id=_env(
                    source,
                    "NANGO_GOOGLE_CALENDAR_INTEGRATION_ID",
                    "google-calendar",
                )
                or "google-calendar",
                nango_calendly_integration_id=_env(source, "NANGO_CALENDLY_INTEGRATION_ID", "calendly") or "calendly",
                nango_salesforce_integration_id=_env(source, "NANGO_SALESFORCE_INTEGRATION_ID", "salesforce")
                or "salesforce",
                nango_hubspot_integration_id=_env(source, "NANGO_HUBSPOT_INTEGRATION_ID", "hubspot") or "hubspot",
                nango_pipedrive_integration_id=_env(source, "NANGO_PIPEDRIVE_INTEGRATION_ID", "pipedrive")
                or "pipedrive",
                nango_slack_integration_id=_env(source, "NANGO_SLACK_INTEGRATION_ID", "slack") or "slack",
                nango_gmail_integration_id=_env(source, "NANGO_GMAIL_INTEGRATION_ID", "gmail") or "gmail",
                nango_outlook_calendar_integration_id=_env(
                    source,
                    "NANGO_OUTLOOK_CALENDAR_INTEGRATION_ID",
                    "outlook",
                )
                or "outlook",
                nango_google_sheets_integration_id=_env(
                    source,
                    "NANGO_GOOGLE_SHEETS_INTEGRATION_ID",
                    "google-sheets",
                )
                or "google-sheets",
                nango_airtable_integration_id=_env(source, "NANGO_AIRTABLE_INTEGRATION_ID", "airtable")
                or "airtable",
                nango_notion_integration_id=_env(source, "NANGO_NOTION_INTEGRATION_ID", "notion") or "notion",
                nango_stripe_integration_id=_env(source, "NANGO_STRIPE_INTEGRATION_ID", "stripe") or "stripe",
                twilio_account_sid=_env(source, "TWILIO_ACCOUNT_SID"),
                twilio_auth_token=_env(source, "TWILIO_AUTH_TOKEN"),
                twilio_from_number=_env(source, "TWILIO_FROM_NUMBER"),
                twilio_messaging_service_sid=_env(source, "TWILIO_MESSAGING_SERVICE_SID"),
                twilio_whatsapp_from=_env(source, "TWILIO_WHATSAPP_FROM"),
                make_webhook_url=_env(source, "MAKE_WEBHOOK_URL"),
                zapier_webhook_url=_env(source, "ZAPIER_WEBHOOK_URL"),
                n8n_webhook_url=_env(source, "N8N_WEBHOOK_URL"),
                generic_webhook_url=_env(source, "VERBATIM_WEBHOOK_URL"),
                zenchef_api_key=_env(source, "ZENCHEF_API_KEY"),
                thefork_api_key=_env(source, "THEFORK_API_KEY"),
                whatsapp_business_access_token=_env(source, "WHATSAPP_BUSINESS_ACCESS_TOKEN"),
                whatsapp_business_phone_number_id=_env(source, "WHATSAPP_BUSINESS_PHONE_NUMBER_ID"),
                stripe_api_key=_env(source, "STRIPE_API_KEY"),
                resend_api_key=_env(source, "RESEND_API_KEY"),
                resend_from_email=_env(source, "RESEND_FROM_EMAIL"),
                default_followup_phone=_env(source, "VERBATIM_DEFAULT_FOLLOWUP_PHONE"),
                default_followup_email=_env(source, "VERBATIM_DEFAULT_FOLLOWUP_EMAIL"),
                followup_sms_default_body=_env(
                    source,
                    "VERBATIM_FOLLOWUP_SMS_DEFAULT_BODY",
                    "Thanks for calling. I will send the property details here shortly.",
                )
                or "Thanks for calling. I will send the property details here shortly.",
                followup_email_default_subject=_env(
                    source,
                    "VERBATIM_FOLLOWUP_EMAIL_DEFAULT_SUBJECT",
                    "Your property follow-up",
                )
                or "Your property follow-up",
                followup_email_default_body=_env(
                    source,
                    "VERBATIM_FOLLOWUP_EMAIL_DEFAULT_BODY",
                    "Thanks for calling. I will send the property details here shortly.",
                )
                or "Thanks for calling. I will send the property details here shortly.",
                default_client_id=_env(source, "VERBATIM_DEFAULT_CLIENT_ID", "demo") or "demo",
                tools_enabled=_env_bool(source, "VERBATIM_TOOLS_ENABLED", True),
                tool_timeout_ms=_env_int(source, "VERBATIM_TOOL_TIMEOUT_MS", 2500) or 2500,
                integrations_db_path=Path(
                    _env(source, "VERBATIM_INTEGRATIONS_DB_PATH", "./data/verbatim/integrations_v2.db")
                    or "./data/verbatim/integrations_v2.db"
                ),
            ),
            session=SessionConfig(
                bot_name=_env(source, "VERBATIM_BOT_NAME", "Verbatim") or "Verbatim",
                room_ttl_seconds=_env_int(source, "VERBATIM_ROOM_TTL_SECONDS", 3600) or 3600,
                idle_timeout_seconds=_env_int(source, "VERBATIM_IDLE_TIMEOUT_SECONDS", 300) or 300,
                user_turn_stop_timeout=_env_float(source, "VERBATIM_USER_TURN_STOP_TIMEOUT", 5.0) or 5.0,
                llm_history_messages=_env_int(source, "VERBATIM_LLM_HISTORY_MESSAGES", 1) or 1,
            ),
        )

    def with_overrides(
        self,
        *,
        transport_provider: Any | None = None,
        stt_provider: Any | None = None,
        deepgram_model: Any | None = None,
        llm_provider: Any | None = None,
        llm_model: Any | None = None,
        daily_geo: Any | None = None,
        force_create_room: Any | None = None,
    ) -> "Settings":
        providers = self.providers
        provider_updates: dict[str, Any] = {}
        if transport_provider is not None:
            provider_updates["transport_provider"] = normalize_transport(transport_provider)
        if stt_provider is not None or deepgram_model is not None:
            stt, model = normalize_stt(
                stt_provider or providers.stt_provider,
                deepgram_model or providers.deepgram_model,
            )
            provider_updates["stt_provider"] = stt
            provider_updates["deepgram_model"] = model
        if llm_provider is not None or llm_model is not None:
            llm, model = normalize_llm(llm_provider or providers.llm_provider, llm_model)
            provider_updates["llm_provider"] = llm
            model_key = {
                "gemini": "gemini_model",
                "openai": "openai_model",
                "groq": "groq_model",
                "qwen": "qwen_model",
                "xai": "xai_model",
                "ultravox": "ultravox_model",
            }.get(llm)
            if model_key and model:
                provider_updates[model_key] = model
        if daily_geo is not None:
            provider_updates["daily_geo"] = str(daily_geo).strip() or None
        if force_create_room is not None:
            provider_updates["daily_force_create_room"] = bool(force_create_room)
        return replace(self, providers=replace(providers, **provider_updates))

    def missing_room_keys(self, transport_provider: str | None = None) -> list[str]:
        provider = normalize_transport(transport_provider or self.providers.transport_provider)
        if provider == "daily":
            if self.providers.daily_room_url and not self.providers.daily_geo and not self.providers.daily_force_create_room:
                return []
            return [] if self.providers.daily_api_key else ["DAILY_API_KEY"]
        if provider == "livekit":
            required = {
                "LIVEKIT_URL": self.providers.livekit_url,
                "LIVEKIT_API_KEY": self.providers.livekit_api_key,
                "LIVEKIT_API_SECRET": self.providers.livekit_api_secret,
            }
            return [key for key, value in required.items() if not value]
        if provider == "hume_evi":
            return []
        return ["VERBATIM_TRANSPORT_PROVIDER"]

    def missing_agent_keys(self) -> list[str]:
        missing = self.missing_room_keys(self.providers.transport_provider)
        if self.providers.transport_provider == "hume_evi":
            return missing_hume_keys(self)
        if self.providers.llm_provider == "ultravox":
            return missing + ([] if self.providers.ultravox_api_key else ["ULTRAVOX_API_KEY"])
        if not self.providers.deepgram_api_key:
            missing.append("DEEPGRAM_API_KEY")
        if not self.voice.cartesia_voice_id:
            missing.append("VERBATIM_CARTESIA_VOICE_ID")
        if not self.providers.cartesia_api_key:
            missing.append("CARTESIA_API_KEY")
        key_by_provider = {
            "gemini": ("GOOGLE_API_KEY", self.providers.google_api_key),
            "openai": ("OPENAI_API_KEY", self.providers.openai_api_key),
            "groq": ("GROQ_API_KEY", self.providers.groq_api_key),
            "qwen": ("QWEN_API_KEY", self.providers.qwen_api_key),
            "xai": ("XAI_API_KEY", self.providers.xai_api_key),
            "mock": (None, "ok"),
        }
        key, value = key_by_provider.get(self.providers.llm_provider, ("VERBATIM_LLM_PROVIDER", None))
        if key and not value:
            missing.append(key)
        return missing


def normalize_transport(value: Any) -> str:
    provider = str(value or "livekit").strip().lower()
    provider = {"lk": "livekit", "live-kit": "livekit", "hume": "hume_evi"}.get(provider, provider)
    if provider not in {"daily", "livekit", "hume_evi"}:
        raise ValueError(f"Unsupported transport provider: {provider}")
    return provider


def normalize_stt(provider_value: Any, model_value: Any | None = None) -> tuple[str, str]:
    provider = str(provider_value or "deepgram").strip().lower()
    model = str(model_value or "").strip()
    if provider in {"nova_3_general", "nova-3-general"}:
        return "deepgram", "nova-3-general"
    if provider == "deepgram_flux":
        return provider, model or "flux-general-en"
    if provider == "deepgram":
        return provider, model or "nova-3-general"
    raise ValueError(f"Unsupported STT provider: {provider}")


def normalize_llm(provider_value: Any, model_value: Any | None = None) -> tuple[str, str | None]:
    provider = str(provider_value or "groq").strip().lower()
    aliases = {
        "google": "gemini",
        "gemini-2.5-flash": "gemini",
        "gpt-4o-mini": "openai",
        "openai_4o_mini": "openai",
        "llama-3.1-8b-instant": "groq",
        "groq_llama_31_8b": "groq",
        "qwen3.5-2b": "qwen",
        "qwen_35_2b": "qwen",
        "grok-4-1-fast-non-reasoning": "xai",
        "xai_grok_41_fast": "xai",
        "fixie-ai/ultravox": "ultravox",
        "ultravox_realtime": "ultravox",
        "mock-immediate": "mock",
    }
    provider = aliases.get(provider, provider)
    if provider not in {"gemini", "openai", "groq", "qwen", "xai", "ultravox", "mock"}:
        raise ValueError(f"Unsupported LLM provider: {provider}")
    return provider, str(model_value).strip() if model_value else None


def validate_runtime_selection(settings: Settings) -> None:
    transport = normalize_transport(settings.providers.transport_provider)
    llm = settings.providers.llm_provider
    if transport == "hume_evi":
        return
    if llm == "ultravox" and transport != "livekit":
        raise ValueError("UltraVox realtime mode requires LiveKit transport.")
    if llm == "hume_evi":
        raise ValueError("Hume EVI uses the Hume transport, not the Pipecat agent endpoint.")


def missing_hume_keys(settings: Settings) -> list[str]:
    missing = []
    if not settings.providers.hume_api_key:
        missing.append("HUME_API_KEY")
    if not settings.providers.hume_secret_key:
        missing.append("HUME_SECRET_KEY")
    return missing


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_env_file(override=True)
    return Settings.from_env()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
