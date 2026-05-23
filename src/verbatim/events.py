from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import threading
import time
import uuid
from typing import Any, Iterable


SCHEMA_VERSION = "verbatim.v2"
SECRET_KEYS = {"token", "authorization", "room_token", "jwt", "api_key", "secret", "access_token"}
_WRITE_LOCK = threading.Lock()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def normalize_event_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9.]+", ".", value.strip()).strip(".").lower()
    cleaned = re.sub(r"[.]+", ".", cleaned)
    return cleaned or "event"


def safe_metadata(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return str(value)[:240]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)[:100]
            if any(secret in key.lower() for secret in SECRET_KEYS):
                result[key] = "[redacted]"
            else:
                result[key] = safe_metadata(raw_value, depth=depth + 1)
        return result
    if isinstance(value, list):
        return [safe_metadata(item, depth=depth + 1) for item in value[:32]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)[:240]


@dataclass
class EventSink:
    event_log_path: Path
    transcript_dir: Path
    call_summary_dir: Path
    session_id: str
    call_id: str
    agent_id: str
    client_id: str
    enabled: bool = True

    def emit(
        self,
        event_name: str,
        *,
        provider: str = "server",
        turn_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "schema_version": SCHEMA_VERSION,
            "session_id": self.session_id,
            "call_id": self.call_id,
            "turn_id": turn_id,
            "agent_id": self.agent_id,
            "client_id": self.client_id,
            "event_name": normalize_event_name(event_name),
            "timestamp_wall_iso": datetime.now(UTC).isoformat(),
            "timestamp_monotonic_ms": round(time.monotonic() * 1000, 3),
            "provider": provider,
            "metadata": safe_metadata(metadata or {}),
        }
        if self.enabled:
            append_jsonl(self.event_log_path, event)
        if event["event_name"] in {"transcript.user", "transcript.assistant"}:
            append_jsonl(self.transcript_dir / f"{self.call_id}.jsonl", event)
        return event

    def write_summary(self, summary: dict[str, Any]) -> None:
        if not self.enabled:
            return
        self.call_summary_dir.mkdir(parents=True, exist_ok=True)
        path = self.call_summary_dir / f"{self.call_id}.json"
        with _WRITE_LOCK:
            path.write_text(json.dumps(safe_metadata(summary), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _WRITE_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def events_for_call(events: Iterable[dict[str, Any]], call_id: str | None) -> list[dict[str, Any]]:
    if not call_id:
        return list(events)
    return [event for event in events if event.get("call_id") == call_id]
