from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from verbatim.config import clear_settings_cache, get_settings
from verbatim.pipelines.pipecat import AgentSession, run_voice_agent


async def amain() -> None:
    payload = json.loads(sys.stdin.read() or "{}")
    clear_settings_cache()
    settings = get_settings().with_overrides(
        transport_provider=payload.get("transport_provider"),
        stt_provider=payload.get("stt_provider"),
        deepgram_model=payload.get("deepgram_model"),
        llm_provider=payload.get("llm_provider"),
        llm_model=payload.get("llm_model"),
    )
    await run_voice_agent(
        settings,
        AgentSession(
            transport_provider=str(payload["transport_provider"]),
            room_url=str(payload["room_url"]),
            room_token=_optional_str(payload.get("room_token")),
            room_name=_optional_str(payload.get("room_name")),
            call_id=_optional_str(payload.get("call_id")),
            session_id=_optional_str(payload.get("session_id")),
            client_id=_optional_str(payload.get("client_id")),
            caller_phone=_optional_str(payload.get("caller_phone")),
            knowledge_base=_optional_str(payload.get("knowledge_base")),
            tools_enabled=bool(payload.get("tools_enabled", False)),
        ),
    )


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
