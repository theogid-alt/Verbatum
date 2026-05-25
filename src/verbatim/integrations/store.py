from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any


CALENDAR_TOOL_NAMES = [
    "check_calendar_availability",
    "check_calendar_conflict",
    "prepare_calendar_booking",
    "confirm_calendar_booking",
    "cancel_calendar_booking",
]


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class IntegrationConnection:
    client_id: str
    provider: str
    integration_key: str
    connection_id: str | None
    status: str
    allowed_tools: list[str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class PendingBooking:
    id: str
    client_id: str
    integration_key: str
    connection_id: str
    status: str
    title: str
    start_iso: str
    end_iso: str
    timezone: str
    attendee_name: str | None
    attendee_email: str | None
    notes: str | None
    created_at: str
    updated_at: str
    confirmed_at: str | None
    external_event_id: str | None
    external_event_url: str | None


class IntegrationStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._initialized = False

    def init_db(self) -> None:
        if self._initialized:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS integration_connections (
                    client_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    integration_key TEXT NOT NULL,
                    connection_id TEXT,
                    status TEXT NOT NULL,
                    allowed_tools_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (client_id, provider, integration_key)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_bookings (
                    id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    integration_key TEXT NOT NULL,
                    connection_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    title TEXT NOT NULL,
                    start_iso TEXT NOT NULL,
                    end_iso TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    attendee_name TEXT,
                    attendee_email TEXT,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    confirmed_at TEXT,
                    external_event_id TEXT,
                    external_event_url TEXT
                )
                """
            )
        self._initialized = True

    def upsert_connection(
        self,
        *,
        client_id: str,
        provider: str,
        integration_key: str,
        connection_id: str | None,
        status: str,
        allowed_tools: list[str] | None = None,
    ) -> IntegrationConnection:
        self.init_db()
        now = utc_now_iso()
        allowed_tools = allowed_tools or CALENDAR_TOOL_NAMES
        existing = self.get_connection(client_id=client_id, provider=provider, integration_key=integration_key)
        created_at = existing.created_at if existing else now
        with self._lock, sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                INSERT INTO integration_connections (
                    client_id, provider, integration_key, connection_id, status,
                    allowed_tools_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(client_id, provider, integration_key)
                DO UPDATE SET
                    connection_id=excluded.connection_id,
                    status=excluded.status,
                    allowed_tools_json=excluded.allowed_tools_json,
                    updated_at=excluded.updated_at
                """,
                (
                    client_id,
                    provider,
                    integration_key,
                    connection_id,
                    status,
                    json.dumps(allowed_tools),
                    created_at,
                    now,
                ),
            )
        return self.get_connection(client_id=client_id, provider=provider, integration_key=integration_key)  # type: ignore[return-value]

    def get_connection(self, *, client_id: str, provider: str, integration_key: str) -> IntegrationConnection | None:
        self.init_db()
        with self._lock, sqlite3.connect(self.path) as conn:
            row = conn.execute(
                """
                SELECT client_id, provider, integration_key, connection_id, status,
                       allowed_tools_json, created_at, updated_at
                FROM integration_connections
                WHERE client_id = ? AND provider = ? AND integration_key = ?
                """,
                (client_id, provider, integration_key),
            ).fetchone()
        return _connection_from_row(row) if row else None

    def list_connections(self, *, client_id: str) -> list[IntegrationConnection]:
        self.init_db()
        with self._lock, sqlite3.connect(self.path) as conn:
            rows = conn.execute(
                """
                SELECT client_id, provider, integration_key, connection_id, status,
                       allowed_tools_json, created_at, updated_at
                FROM integration_connections
                WHERE client_id = ?
                ORDER BY integration_key
                """,
                (client_id,),
            ).fetchall()
        return [_connection_from_row(row) for row in rows]

    def delete_connection(self, *, client_id: str, provider: str, integration_key: str) -> bool:
        self.init_db()
        with self._lock, sqlite3.connect(self.path) as conn:
            cursor = conn.execute(
                """
                DELETE FROM integration_connections
                WHERE client_id = ? AND provider = ? AND integration_key = ?
                """,
                (client_id, provider, integration_key),
            )
        return bool(cursor.rowcount)

    def create_pending_booking(
        self,
        *,
        booking_id: str,
        client_id: str,
        integration_key: str,
        connection_id: str,
        title: str,
        start_iso: str,
        end_iso: str,
        timezone: str,
        attendee_name: str | None = None,
        attendee_email: str | None = None,
        notes: str | None = None,
    ) -> PendingBooking:
        self.init_db()
        now = utc_now_iso()
        with self._lock, sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                INSERT INTO pending_bookings (
                    id, client_id, integration_key, connection_id, status,
                    title, start_iso, end_iso, timezone, attendee_name, attendee_email,
                    notes, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    booking_id,
                    client_id,
                    integration_key,
                    connection_id,
                    title,
                    start_iso,
                    end_iso,
                    timezone,
                    attendee_name,
                    attendee_email,
                    notes,
                    now,
                    now,
                ),
            )
        booking = self.get_pending_booking(booking_id)
        if not booking:
            raise RuntimeError("Pending booking insert failed.")
        return booking

    def get_pending_booking(self, booking_id: str) -> PendingBooking | None:
        self.init_db()
        with self._lock, sqlite3.connect(self.path) as conn:
            row = conn.execute(
                """
                SELECT id, client_id, integration_key, connection_id, status, title,
                       start_iso, end_iso, timezone, attendee_name, attendee_email,
                       notes, created_at, updated_at, confirmed_at, external_event_id,
                       external_event_url
                FROM pending_bookings
                WHERE id = ?
                """,
                (booking_id,),
            ).fetchone()
        return _booking_from_row(row) if row else None

    def mark_booking_confirmed(
        self,
        *,
        booking_id: str,
        external_event_id: str | None,
        external_event_url: str | None,
    ) -> PendingBooking:
        self.init_db()
        now = utc_now_iso()
        with self._lock, sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                UPDATE pending_bookings
                SET status = 'confirmed',
                    confirmed_at = COALESCE(confirmed_at, ?),
                    updated_at = ?,
                    external_event_id = COALESCE(external_event_id, ?),
                    external_event_url = COALESCE(external_event_url, ?)
                WHERE id = ?
                """,
                (now, now, external_event_id, external_event_url, booking_id),
            )
        booking = self.get_pending_booking(booking_id)
        if not booking:
            raise RuntimeError("Confirmed booking was not found.")
        return booking

    def mark_booking_cancelled(self, *, booking_id: str) -> PendingBooking:
        self.init_db()
        now = utc_now_iso()
        with self._lock, sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                UPDATE pending_bookings
                SET status = 'cancelled',
                    updated_at = ?
                WHERE id = ?
                """,
                (now, booking_id),
            )
        booking = self.get_pending_booking(booking_id)
        if not booking:
            raise RuntimeError("Cancelled booking was not found.")
        return booking

    def latest_booking(
        self,
        *,
        client_id: str,
        integration_key: str,
        status: str = "confirmed",
    ) -> PendingBooking | None:
        self.init_db()
        with self._lock, sqlite3.connect(self.path) as conn:
            row = conn.execute(
                """
                SELECT id, client_id, integration_key, connection_id, status, title,
                       start_iso, end_iso, timezone, attendee_name, attendee_email,
                       notes, created_at, updated_at, confirmed_at, external_event_id,
                       external_event_url
                FROM pending_bookings
                WHERE client_id = ?
                  AND integration_key = ?
                  AND status = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (client_id, integration_key, status),
            ).fetchone()
        return _booking_from_row(row) if row else None


def _connection_from_row(row: Any) -> IntegrationConnection:
    return IntegrationConnection(
        client_id=row[0],
        provider=row[1],
        integration_key=row[2],
        connection_id=row[3],
        status=row[4],
        allowed_tools=json.loads(row[5] or "[]"),
        created_at=row[6],
        updated_at=row[7],
    )


def _booking_from_row(row: Any) -> PendingBooking:
    return PendingBooking(
        id=row[0],
        client_id=row[1],
        integration_key=row[2],
        connection_id=row[3],
        status=row[4],
        title=row[5],
        start_iso=row[6],
        end_iso=row[7],
        timezone=row[8],
        attendee_name=row[9],
        attendee_email=row[10],
        notes=row[11],
        created_at=row[12],
        updated_at=row[13],
        confirmed_at=row[14],
        external_event_id=row[15],
        external_event_url=row[16],
    )
