from __future__ import annotations

from dataclasses import replace
from typing import Any


def settings_with_stt_override(
    settings,
    *,
    stt_provider: Any | None,
    deepgram_model: Any | None,
):
    provider = str(stt_provider or settings.providers.stt_provider).strip().lower()
    model = str(deepgram_model or settings.providers.deepgram_model).strip()
    if provider in {"nova_3_general", "nova-3-general"}:
        provider = "deepgram"
        model = "nova-3-general"
    if provider not in {"deepgram", "deepgram_flux"}:
        raise ValueError(f"Unsupported STT provider: {provider}")
    if provider == "deepgram_flux" and model.startswith("nova-"):
        model = "flux-general-en"
    if provider == "deepgram" and not model:
        model = "nova-3-general"
    return replace(
        settings,
        providers=replace(
            settings.providers,
            stt_provider=provider,
            deepgram_model=model,
        ),
    )


def settings_with_llm_override(
    settings,
    *,
    llm_provider: Any | None,
    llm_model: Any | None,
):
    provider = str(llm_provider or settings.providers.llm_provider).strip().lower()
    model = str(llm_model or "").strip()
    aliases = {
        "google": "gemini",
        "gemini_flash": "gemini",
        "gemini-2.5-flash": "gemini",
        "openai_4o_mini": "openai",
        "gpt-4o-mini": "openai",
        "groq_llama_31_8b": "groq",
        "llama-3.1-8b-instant": "groq",
        "qwen_35_2b": "qwen",
        "qwen3.5-2b": "qwen",
        "qwen3.5_2b": "qwen",
        "qwen3-5_2b": "qwen",
        "xai_grok_41_fast": "xai",
        "grok_41_fast": "xai",
        "grok-4-1-fast-non-reasoning": "xai",
        "ultravox_realtime": "ultravox",
        "fixie-ai/ultravox": "ultravox",
        "mock-immediate": "mock",
    }
    provider = aliases.get(provider, provider)
    if provider not in {"gemini", "openai", "groq", "qwen", "xai", "ultravox", "mock"}:
        raise ValueError(f"Unsupported LLM provider: {provider}")

    updates: dict[str, Any] = {"llm_provider": provider}
    if provider == "gemini":
        updates["gemini_model"] = model or settings.providers.gemini_model or "gemini-2.5-flash"
    elif provider == "openai":
        updates["openai_model"] = model or settings.providers.openai_model or "gpt-4o-mini"
    elif provider == "groq":
        updates["groq_model"] = model or settings.providers.groq_model or "llama-3.1-8b-instant"
    elif provider == "qwen":
        updates["qwen_model"] = model or settings.providers.qwen_model or "qwen3.5-2b"
    elif provider == "xai":
        updates["xai_model"] = (
            model or settings.providers.xai_model or "grok-4-1-fast-non-reasoning"
        )
    elif provider == "ultravox":
        updates["ultravox_model"] = model or settings.providers.ultravox_model or "fixie-ai/ultravox"
    return replace(settings, providers=replace(settings.providers, **updates))


def settings_with_transport_override(settings, *, transport_provider: Any | None):
    provider = str(transport_provider or settings.providers.transport_provider or "daily").strip().lower()
    aliases = {
        "lk": "livekit",
        "live-kit": "livekit",
    }
    provider = aliases.get(provider, provider)
    if provider not in {"daily", "livekit"}:
        raise ValueError(f"Unsupported transport provider: {provider}")
    return replace(settings, providers=replace(settings.providers, transport_provider=provider))


def settings_with_runtime_overrides(
    settings,
    *,
    transport_provider: Any | None = None,
    stt_provider: Any | None,
    deepgram_model: Any | None,
    llm_provider: Any | None,
    llm_model: Any | None,
):
    settings = settings_with_transport_override(settings, transport_provider=transport_provider)
    settings = settings_with_stt_override(
        settings,
        stt_provider=stt_provider,
        deepgram_model=deepgram_model,
    )
    return settings_with_llm_override(
        settings,
        llm_provider=llm_provider,
        llm_model=llm_model,
    )
