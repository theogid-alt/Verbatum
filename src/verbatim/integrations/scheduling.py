from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
import re
from typing import Any
from zoneinfo import ZoneInfo

from verbatim.events import new_id
from verbatim.integrations.nango import NangoClient, NangoError, parse_iso_datetime
from verbatim.integrations.store import CALENDAR_TOOL_NAMES, IntegrationStore, PendingBooking


CONFIRM_RE = re.compile(
    r"\b(yes|yeah|yep|ok|okay|correct|confirm|confirmed|book it|go ahead|that works|works for me|sure|"
    r"please do|let'?s do it|do it)\b",
    re.I,
)
REJECT_RE = re.compile(r"\b(no|nope|not yet|wait|hold on|don't|do not|cancel|wrong)\b", re.I)
CANCEL_RE = re.compile(r"\b(delete|remove|cancel|clear|take it off)\b", re.I)


class SchedulingService:
    def __init__(
        self,
        *,
        store: IntegrationStore,
        nango: NangoClient,
        client_id: str,
        integration_key: str,
    ) -> None:
        self.store = store
        self.nango = nango
        self.client_id = client_id
        self.integration_key = integration_key

    async def check_calendar_availability(
        self,
        *,
        date_iso: str | None = None,
        timezone: str = "Europe/Paris",
        duration_minutes: int = 30,
    ) -> dict[str, Any]:
        connection = self._connection()
        if not connection:
            return _missing_connection()
        duration_minutes = min(max(int(duration_minutes or 30), 15), 180)
        start, end = _business_window(date_iso=date_iso, timezone=timezone)
        try:
            freebusy = await self.nango.google_calendar_freebusy(
                connection_id=connection.connection_id or "",
                integration_key=self.integration_key,
                time_min=start.isoformat(),
                time_max=end.isoformat(),
            )
        except NangoError as exc:
            return _safe_failure("calendar_availability_failed", str(exc))
        busy = _busy_ranges(freebusy)
        slots = _available_slots(start, end, busy, duration_minutes=duration_minutes)[:4]
        return {
            "ok": True,
            "outcome": "available_slots",
            "client_id": self.client_id,
            "integration_provider": "nango",
            "integration_key": self.integration_key,
            "slots": slots,
            "message": _slots_message(slots),
        }

    async def check_calendar_conflict(
        self,
        *,
        start_iso: str,
        end_iso: str,
        timezone: str = "Europe/Paris",
    ) -> dict[str, Any]:
        connection = self._connection()
        if not connection:
            return _missing_connection()
        try:
            start = parse_iso_datetime(start_iso)
            end = parse_iso_datetime(end_iso)
        except ValueError:
            return _safe_failure("invalid_calendar_time", "The calendar time was not a valid ISO datetime.")
        if end <= start:
            return _safe_failure("invalid_calendar_time", "The calendar end must be after the start.")
        day_start = start.replace(hour=9, minute=0, second=0, microsecond=0)
        day_end = start.replace(hour=18, minute=0, second=0, microsecond=0)
        try:
            freebusy = await self.nango.google_calendar_freebusy(
                connection_id=connection.connection_id or "",
                integration_key=self.integration_key,
                time_min=day_start.isoformat(),
                time_max=day_end.isoformat(),
            )
        except NangoError as exc:
            return _safe_failure("calendar_conflict_check_failed", str(exc))
        busy = _busy_ranges(freebusy)
        conflicts = [
            {"start_iso": busy_start.isoformat(), "end_iso": busy_end.isoformat()}
            for busy_start, busy_end in busy
            if _overlaps(start, end, busy_start, busy_end)
        ]
        duration_minutes = max(15, int((end - start).total_seconds() // 60))
        min_suggestion_start = max(end, datetime.now(start.tzinfo or ZoneInfo(timezone)) + timedelta(minutes=30))
        suggested_slots = [
            slot
            for slot in _available_slots(day_start, day_end, busy, duration_minutes=duration_minutes)
            if parse_iso_datetime(slot["start_iso"]) >= min_suggestion_start
        ][:3]
        if conflicts and not suggested_slots:
            suggested_slots = await self._next_available_slots_after(
                start=end + timedelta(days=1),
                duration_minutes=duration_minutes,
                timezone=timezone,
            )
        return {
            "ok": True,
            "outcome": "calendar_conflict_checked",
            "client_id": self.client_id,
            "integration_provider": "nango",
            "integration_key": self.integration_key,
            "has_conflict": bool(conflicts),
            "conflicts": conflicts[:4],
            "suggested_slots": suggested_slots,
            "checked_slot": {
                "start_iso": start.isoformat(),
                "end_iso": end.isoformat(),
                "timezone": timezone,
            },
            "message": "That time is busy." if conflicts else "That time is open.",
        }

    async def prepare_calendar_booking(
        self,
        *,
        start_iso: str,
        end_iso: str,
        timezone: str = "Europe/Paris",
        title: str = "Property viewing",
        attendee_name: str | None = None,
        attendee_email: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        connection = self._connection()
        if not connection:
            return _missing_connection()
        try:
            start = parse_iso_datetime(start_iso)
            end = parse_iso_datetime(end_iso)
        except ValueError:
            return _safe_failure("invalid_booking_time", "The booking time was not a valid ISO datetime.")
        if end <= start:
            return _safe_failure("invalid_booking_time", "The booking end must be after the start.")
        booking = self.store.create_pending_booking(
            booking_id=new_id("booking"),
            client_id=self.client_id,
            integration_key=self.integration_key,
            connection_id=connection.connection_id or "",
            title=(title or "Property viewing")[:120],
            start_iso=start.isoformat(),
            end_iso=end.isoformat(),
            timezone=timezone,
            attendee_name=attendee_name,
            attendee_email=attendee_email,
            notes=notes,
        )
        return {
            "ok": True,
            "outcome": "confirmation_required",
            "requires_confirmation": True,
            "pending_booking_id": booking.id,
            "start_iso": booking.start_iso,
            "end_iso": booking.end_iso,
            "confirmation_prompt": "Please confirm before I book it.",
        }

    async def confirm_calendar_booking(
        self,
        *,
        pending_booking_id: str,
        confirmation_text: str | None = None,
        latest_user_text: str | None = None,
    ) -> dict[str, Any]:
        text = f"{confirmation_text or ''} {latest_user_text or ''}".strip()
        booking = self.store.get_pending_booking(pending_booking_id)
        if not booking:
            return _safe_failure("missing_pending_booking", "No pending booking proposal was found.")
        if booking.client_id != self.client_id:
            return _safe_failure("wrong_client", "That booking proposal belongs to a different client.")
        if booking.status == "confirmed":
            return _booking_confirmed_payload(booking, idempotent=True)
        if not _explicitly_confirmed(text):
            return {
                "ok": False,
                "outcome": "confirmation_required",
                "requires_confirmation": True,
                "message": "Ask the caller for a clear yes before booking.",
            }
        conflict = await self.check_calendar_conflict(
            start_iso=booking.start_iso,
            end_iso=booking.end_iso,
            timezone=booking.timezone,
        )
        if conflict.get("ok") and conflict.get("has_conflict"):
            return {
                "ok": False,
                "outcome": "slot_conflict",
                "has_conflict": True,
                "conflicts": conflict.get("conflicts") or [],
                "suggested_slots": conflict.get("suggested_slots") or [],
                "message": "That time is already busy, so I did not book it.",
            }
        if not conflict.get("ok"):
            return conflict
        try:
            event = await self.nango.google_calendar_create_event(
                connection_id=booking.connection_id,
                integration_key=booking.integration_key,
                title=booking.title,
                start_iso=booking.start_iso,
                end_iso=booking.end_iso,
                timezone=booking.timezone,
                attendee_email=booking.attendee_email,
                notes=booking.notes,
            )
        except NangoError as exc:
            return _safe_failure("calendar_booking_failed", str(exc))
        confirmed = self.store.mark_booking_confirmed(
            booking_id=booking.id,
            external_event_id=str(event.get("id") or "") or None,
            external_event_url=str(event.get("htmlLink") or event.get("hangoutLink") or "") or None,
        )
        return _booking_confirmed_payload(confirmed, idempotent=False)

    async def cancel_calendar_booking(
        self,
        *,
        booking_id: str | None = None,
        confirmation_text: str | None = None,
        latest_user_text: str | None = None,
    ) -> dict[str, Any]:
        text = f"{confirmation_text or ''} {latest_user_text or ''}".strip()
        booking = self.store.get_pending_booking(booking_id) if booking_id else self.store.latest_booking(
            client_id=self.client_id,
            integration_key=self.integration_key,
            status="confirmed",
        )
        if not booking:
            return _safe_failure("missing_confirmed_booking", "No confirmed booking from Verbatim was found to remove.")
        if booking.client_id != self.client_id:
            return _safe_failure("wrong_client", "That booking belongs to a different client.")
        if booking.status == "cancelled":
            return _booking_cancelled_payload(booking, idempotent=True)
        if booking.status != "confirmed":
            return _safe_failure("booking_not_confirmed", "Only confirmed bookings can be removed.")
        if not _explicitly_cancelled(text):
            return {
                "ok": False,
                "outcome": "cancellation_confirmation_required",
                "requires_confirmation": True,
                "message": "Ask the caller for a clear yes before removing it.",
            }
        if not booking.external_event_id:
            return _safe_failure("missing_external_event_id", "The calendar event id was not stored, so I cannot remove it safely.")
        try:
            await self.nango.google_calendar_delete_event(
                connection_id=booking.connection_id,
                integration_key=booking.integration_key,
                event_id=booking.external_event_id,
            )
        except NangoError as exc:
            return _safe_failure("calendar_cancel_failed", str(exc))
        cancelled = self.store.mark_booking_cancelled(booking_id=booking.id)
        return _booking_cancelled_payload(cancelled, idempotent=False)

    def _connection(self):
        return self.store.get_connection(
            client_id=self.client_id,
            provider="nango",
            integration_key=self.integration_key,
        )

    async def _next_available_slots_after(
        self,
        *,
        start: datetime,
        duration_minutes: int,
        timezone: str,
    ) -> list[dict[str, str]]:
        connection = self._connection()
        if not connection:
            return []
        cursor = start.astimezone(ZoneInfo(timezone)) if start.tzinfo else start.replace(tzinfo=ZoneInfo(timezone))
        for offset in range(0, 7):
            day = (cursor + timedelta(days=offset)).replace(hour=9, minute=0, second=0, microsecond=0)
            day_end = day.replace(hour=18, minute=0, second=0, microsecond=0)
            try:
                freebusy = await self.nango.google_calendar_freebusy(
                    connection_id=connection.connection_id or "",
                    integration_key=self.integration_key,
                    time_min=day.isoformat(),
                    time_max=day_end.isoformat(),
                )
            except NangoError:
                return []
            slots = _available_slots(day, day_end, _busy_ranges(freebusy), duration_minutes=duration_minutes)
            if slots:
                return slots[:3]
        return []


def _explicitly_confirmed(text: str) -> bool:
    if not text or REJECT_RE.search(text):
        return False
    return bool(CONFIRM_RE.search(text))


def _explicitly_cancelled(text: str) -> bool:
    return bool(text and CANCEL_RE.search(text))


def _missing_connection() -> dict[str, Any]:
    return {
        "ok": False,
        "outcome": "missing_connection",
        "requires_connection": True,
        "message": "Calendar is not connected. Offer WhatsApp follow-up instead.",
    }


def _safe_failure(outcome: str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "outcome": outcome,
        "message": message[:240],
    }


def _business_window(*, date_iso: str | None, timezone: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(timezone)
    if date_iso:
        base = parse_iso_datetime(date_iso)
        if base.tzinfo is None:
            base = base.replace(tzinfo=tz)
        else:
            base = base.astimezone(tz)
    else:
        # If the caller has not named a day, avoid absurd "30 minutes from now"
        # viewing proposals. Default to the next calendar day and let callers
        # ask for today explicitly when they mean it.
        base = datetime.now(tz) + timedelta(days=1)
    start = base.replace(hour=9, minute=0, second=0, microsecond=0)
    if start < datetime.now(tz):
        start = datetime.now(tz).replace(second=0, microsecond=0) + timedelta(minutes=30)
    end = start.replace(hour=18, minute=0, second=0, microsecond=0)
    if end <= start:
        start = (start + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        end = start.replace(hour=18, minute=0, second=0, microsecond=0)
    return start, end


def _busy_ranges(freebusy: dict[str, Any]) -> list[tuple[datetime, datetime]]:
    calendars = freebusy.get("calendars") if isinstance(freebusy, dict) else {}
    primary = calendars.get("primary") if isinstance(calendars, dict) else None
    if primary is None and isinstance(calendars, dict) and calendars:
        primary = next(iter(calendars.values()))
    busy_items = primary.get("busy", []) if isinstance(primary, dict) else []
    ranges: list[tuple[datetime, datetime]] = []
    for item in busy_items:
        try:
            ranges.append((parse_iso_datetime(str(item["start"])), parse_iso_datetime(str(item["end"]))))
        except (KeyError, TypeError, ValueError):
            continue
    return ranges


def _available_slots(
    start: datetime,
    end: datetime,
    busy: list[tuple[datetime, datetime]],
    *,
    duration_minutes: int,
) -> list[dict[str, str]]:
    slots: list[dict[str, str]] = []
    cursor = start
    duration = timedelta(minutes=duration_minutes)
    while cursor + duration <= end and len(slots) < 4:
        slot_end = cursor + duration
        if not any(_overlaps(cursor, slot_end, busy_start, busy_end) for busy_start, busy_end in busy):
            slots.append({"start_iso": cursor.isoformat(), "end_iso": slot_end.isoformat()})
        cursor += timedelta(minutes=30)
    return slots


def _overlaps(start: datetime, end: datetime, busy_start: datetime, busy_end: datetime) -> bool:
    if busy_start.tzinfo is None and start.tzinfo is not None:
        busy_start = busy_start.replace(tzinfo=start.tzinfo)
    if busy_end.tzinfo is None and end.tzinfo is not None:
        busy_end = busy_end.replace(tzinfo=end.tzinfo)
    return start < busy_end and busy_start < end


def _slots_message(slots: list[dict[str, str]]) -> str:
    if not slots:
        return "No open slots were found in that window."
    return "Found a few viewing slots."


def _booking_confirmed_payload(booking: PendingBooking, *, idempotent: bool) -> dict[str, Any]:
    return {
        "ok": True,
        "outcome": "booking_confirmed",
        "idempotent": idempotent,
        "booking": {
            key: value
            for key, value in asdict(booking).items()
            if key not in {"connection_id"}
        },
        "message": "The calendar booking is confirmed.",
    }


def _booking_cancelled_payload(booking: PendingBooking, *, idempotent: bool) -> dict[str, Any]:
    return {
        "ok": True,
        "outcome": "booking_cancelled",
        "idempotent": idempotent,
        "booking": {
            key: value
            for key, value in asdict(booking).items()
            if key not in {"connection_id", "external_event_id"}
        },
        "message": "The calendar booking is cancelled.",
    }
