from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
from queue import Queue
import threading
import time
from typing import Any, Literal
from uuid import uuid4

from verbatim.config import InstrumentationConfig


SCHEMA_VERSION = "0.1"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def normalize_event_name(event_name: str) -> str:
    normalized = event_name.strip().lower().replace(" ", ".")
    if normalized.startswith("atts."):
        normalized = "tts." + normalized.removeprefix("atts.")
    return normalized


@dataclass(frozen=True)
class Event:
    schema_version: str
    session_id: str
    call_id: str
    turn_id: str | None
    agent_id: str
    client_id: str
    event_name: str
    timestamp_wall_iso: str
    timestamp_monotonic_ms: float
    provider: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EventLogger:
    def __init__(
        self,
        config: InstrumentationConfig,
        *,
        session_id: str,
        call_id: str,
        agent_id: str,
        client_id: str,
    ) -> None:
        self.config = config
        self.session_id = session_id
        self.call_id = call_id
        self.agent_id = agent_id
        self.client_id = client_id
        self._lock = threading.Lock()
        self._write_queue: Queue[tuple[Literal["json", "jsonl"], Path, dict[str, Any]] | None] = Queue()
        self._writer = threading.Thread(
            target=self._drain_write_queue,
            name=f"verbatim-event-writer-{call_id}",
            daemon=True,
        )
        self._writer.start()

    def emit(
        self,
        event_name: str,
        *,
        turn_id: str | None = None,
        provider: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Event:
        event = Event(
            schema_version=SCHEMA_VERSION,
            session_id=self.session_id,
            call_id=self.call_id,
            turn_id=turn_id,
            agent_id=self.agent_id,
            client_id=self.client_id,
            event_name=normalize_event_name(event_name),
            timestamp_wall_iso=datetime.now(UTC).isoformat(),
            timestamp_monotonic_ms=round(time.monotonic() * 1000, 3),
            provider=provider,
            metadata=metadata or {},
        )
        if self.config.enable_jsonl_events:
            self._append_jsonl(self.config.event_log_path, event.to_dict())
        return event

    def write_call_summary(self, summary: dict[str, Any]) -> Path:
        path = self.config.call_summary_dir / f"{self.call_id}.json"
        self._write_queue.put(("json", path, summary))
        return path

    def write_transcript(self, item: dict[str, Any]) -> Path:
        self.config.transcript_dir.mkdir(parents=True, exist_ok=True)
        path = self.config.transcript_dir / f"{self.call_id}.jsonl"
        self._append_jsonl(path, item)
        return path

    def write_slow_turn_trace(self, turn_id: str, trace: dict[str, Any]) -> Path:
        path = self.config.slow_turn_trace_dir / self.call_id / f"{turn_id}.json"
        self._write_queue.put(("json", path, trace))
        return path

    def _append_jsonl(self, path: Path, payload: dict[str, Any]) -> None:
        self._write_queue.put(("jsonl", path, payload))

    def flush(self) -> None:
        self._write_queue.join()

    def close(self) -> None:
        self.flush()
        self._write_queue.put(None)
        self._writer.join(timeout=2)

    def _drain_write_queue(self) -> None:
        while True:
            item = self._write_queue.get()
            try:
                if item is None:
                    return
                mode, path, payload = item
                path.parent.mkdir(parents=True, exist_ok=True)
                with self._lock:
                    if mode == "json":
                        path.write_text(
                            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
                            encoding="utf-8",
                        )
                    else:
                        with path.open("a", encoding="utf-8") as handle:
                            handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
            finally:
                self._write_queue.task_done()


def load_events(path: str | Path) -> list[dict[str, Any]]:
    event_path = Path(path)
    if not event_path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in event_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events
