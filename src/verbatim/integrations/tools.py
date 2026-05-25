from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import re
import time
from typing import Any, Callable
from zoneinfo import ZoneInfo

from verbatim.config import Settings
from verbatim.integrations.followup import FollowupService, followup_tools_ready
from verbatim.integrations.nango import NangoClient
from verbatim.integrations.scheduling import SchedulingService
from verbatim.integrations.store import IntegrationStore


def scheduling_tool_names() -> list[str]:
    return [
        "check_calendar_availability",
        "check_calendar_conflict",
        "prepare_calendar_booking",
        "confirm_calendar_booking",
        "cancel_calendar_booking",
    ]


def followup_tool_names() -> list[str]:
    return [
        "send_sms_followup",
    ]


def verbatim_tool_names() -> list[str]:
    return scheduling_tool_names() + followup_tool_names()


def build_scheduling_tools_schema(enabled_tool_names: set[str] | None = None):
    from pipecat.adapters.schemas.function_schema import FunctionSchema
    from pipecat.adapters.schemas.tools_schema import ToolsSchema

    enabled_tool_names = enabled_tool_names or set(verbatim_tool_names())
    tools = [
            FunctionSchema(
                name="check_calendar_availability",
                description="Check the connected Google Calendar and return two to four available viewing slots. Read-only.",
                properties={
                    "date_iso": {
                        "type": "string",
                        "description": "ISO date or datetime to check, for example 2026-05-23.",
                    },
                    "timezone": {
                        "type": "string",
                        "description": "IANA timezone. Use Europe/Paris if the caller does not specify one.",
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Requested appointment length in minutes.",
                    },
                },
                required=[],
            ),
            FunctionSchema(
                name="check_calendar_conflict",
                description="Check whether a specific calendar time is already busy. Read-only.",
                properties={
                    "start_iso": {"type": "string", "description": "Start datetime in ISO format."},
                    "end_iso": {"type": "string", "description": "End datetime in ISO format."},
                    "timezone": {"type": "string", "description": "IANA timezone for the appointment."},
                },
                required=["start_iso", "end_iso"],
            ),
            FunctionSchema(
                name="prepare_calendar_booking",
                description="Prepare a pending calendar booking proposal. This does not create an external calendar event.",
                properties={
                    "start_iso": {"type": "string", "description": "Confirmed start datetime in ISO format."},
                    "end_iso": {"type": "string", "description": "Confirmed end datetime in ISO format."},
                    "timezone": {"type": "string", "description": "IANA timezone for the appointment."},
                    "title": {"type": "string", "description": "Short event title."},
                    "attendee_name": {"type": "string", "description": "Caller name, if known."},
                    "attendee_email": {"type": "string", "description": "Caller email, if known."},
                    "notes": {"type": "string", "description": "Short private notes for the event."},
                },
                required=["start_iso", "end_iso"],
            ),
            FunctionSchema(
                name="confirm_calendar_booking",
                description="Create the calendar event only after a pending proposal exists and the latest user turn explicitly confirms it.",
                properties={
                    "pending_booking_id": {"type": "string", "description": "Pending booking proposal id."},
                    "confirmation_text": {
                        "type": "string",
                        "description": "The user's latest explicit confirmation text, such as yes or book it.",
                    },
                },
                required=["pending_booking_id"],
            ),
            FunctionSchema(
                name="cancel_calendar_booking",
                description="Remove the latest Verbatim-created calendar booking only after the user explicitly asks to delete, cancel, or remove it.",
                properties={
                    "booking_id": {"type": "string", "description": "Known Verbatim booking id, if available."},
                    "confirmation_text": {
                        "type": "string",
                        "description": "The user's latest explicit cancellation text, such as delete it or cancel it.",
                    },
                },
                required=[],
            ),
            FunctionSchema(
                name="send_sms_followup",
                description=(
                    "Send a short SMS follow-up to the caller phone number attached to this call. "
                    "Never ask the caller to dictate a phone number."
                ),
                properties={
                    "body": {"type": "string", "description": "Brief message body, spoken-call friendly."},
                    "channel": {"type": "string", "description": "Use sms."},
                },
                required=[],
            ),
    ]
    return ToolsSchema(standard_tools=[tool for tool in tools if tool.name in enabled_tool_names])


class SchedulingToolRuntime:
    def __init__(
        self,
        *,
        settings: Settings,
        client_id: str,
        recorder: Any,
        caller_phone: str | None = None,
        enabled_tools: list[str] | set[str] | None = None,
        nango_client_factory: Callable[[Settings], NangoClient] | None = None,
    ) -> None:
        self.settings = settings
        self.client_id = client_id
        self.caller_phone = _trusted_caller_phone(caller_phone)
        self.enabled_tools = set(enabled_tools or verbatim_tool_names())
        self.recorder = recorder
        self.integration_key = settings.integrations.nango_google_calendar_integration_id
        self.store = IntegrationStore(settings.integrations.integrations_db_path)
        self.nango = nango_client_factory(settings) if nango_client_factory else NangoClient(settings)
        self.service = SchedulingService(
            store=self.store,
            nango=self.nango,
            client_id=client_id,
            integration_key=self.integration_key,
        )
        self.followup = FollowupService(settings=settings, client_id=client_id)
        self.timeout_secs = max(settings.integrations.tool_timeout_ms, 1) / 1000

    def _timeout_for(self, tool_name: str) -> float:
        if tool_name in {"confirm_calendar_booking", "cancel_calendar_booking"}:
            return max(self.timeout_secs, 4.5)
        if tool_name == "send_sms_followup":
            return max(self.timeout_secs, 4.0)
        return self.timeout_secs

    def register(self, llm: Any, context: Any, *, expose_context_tools: bool = False) -> Any | None:
        if not hasattr(llm, "register_function"):
            self._emit(
                "tool.call.failed",
                tool_name="scheduling",
                outcome="unsupported_llm",
                metadata={"message": "Selected LLM service does not support registered functions."},
            )
            return None
        tools_schema = build_scheduling_tools_schema(self.enabled_tools)
        if expose_context_tools:
            context.set_tools(tools_schema)
            context.set_tool_choice("auto")
        for name in verbatim_tool_names():
            if name not in self.enabled_tools:
                continue
            llm.register_function(
                name,
                self._handler_for(name),
                cancel_on_interruption=True,
                timeout_secs=self.timeout_secs,
            )
        return tools_schema

    async def run_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return await self._run_tool(tool_name, arguments)

    def _handler_for(self, tool_name: str):
        async def handler(params):
            arguments = dict(params.arguments or {})
            result = await self._run_tool(tool_name, arguments)
            await params.result_callback(result)

        return handler

    async def _run_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        timeout_secs = self._timeout_for(tool_name)
        self._emit("tool.call.started", tool_name=tool_name, outcome="started")
        try:
            if tool_name not in self.enabled_tools:
                result = {"ok": False, "outcome": "tool_disabled", "message": f"{tool_name} is disabled for this agent."}
            elif tool_name == "check_calendar_availability":
                result = await asyncio.wait_for(
                    self.service.check_calendar_availability(
                        date_iso=_optional_str(arguments.get("date_iso")),
                        timezone=str(arguments.get("timezone") or "Europe/Paris"),
                        duration_minutes=int(arguments.get("duration_minutes") or 30),
                    ),
                    timeout=timeout_secs,
                )
            elif tool_name == "check_calendar_conflict":
                result = await asyncio.wait_for(
                    self.service.check_calendar_conflict(
                        start_iso=str(arguments.get("start_iso") or ""),
                        end_iso=str(arguments.get("end_iso") or ""),
                        timezone=str(arguments.get("timezone") or "Europe/Paris"),
                    ),
                    timeout=timeout_secs,
                )
            elif tool_name == "prepare_calendar_booking":
                result = await asyncio.wait_for(
                    self.service.prepare_calendar_booking(
                        start_iso=str(arguments.get("start_iso") or ""),
                        end_iso=str(arguments.get("end_iso") or ""),
                        timezone=str(arguments.get("timezone") or "Europe/Paris"),
                        title=str(arguments.get("title") or "Property viewing"),
                        attendee_name=_optional_str(arguments.get("attendee_name")),
                        attendee_email=_optional_str(arguments.get("attendee_email")),
                        notes=_optional_str(arguments.get("notes")),
                    ),
                    timeout=timeout_secs,
                )
            elif tool_name == "confirm_calendar_booking":
                result = await asyncio.wait_for(
                    self.service.confirm_calendar_booking(
                        pending_booking_id=str(arguments.get("pending_booking_id") or ""),
                        confirmation_text=_optional_str(arguments.get("confirmation_text")),
                        latest_user_text=getattr(self.recorder, "latest_user_text", None),
                    ),
                    timeout=timeout_secs,
                )
            elif tool_name == "cancel_calendar_booking":
                result = await asyncio.wait_for(
                    self.service.cancel_calendar_booking(
                        booking_id=_optional_str(arguments.get("booking_id")),
                        confirmation_text=_optional_str(arguments.get("confirmation_text")),
                        latest_user_text=getattr(self.recorder, "latest_user_text", None),
                    ),
                    timeout=timeout_secs,
                )
            elif tool_name == "send_sms_followup":
                result = await asyncio.wait_for(
                    self.followup.send_sms_followup(
                        to_phone=self.caller_phone,
                        body=str(arguments.get("body") or self.settings.integrations.followup_sms_default_body),
                        channel=str(arguments.get("channel") or "sms"),
                    ),
                    timeout=timeout_secs,
                )
            elif tool_name == "send_email_followup":
                result = await asyncio.wait_for(
                    self.followup.send_email_followup(
                        to_email=_optional_str(arguments.get("to_email")),
                        subject=str(arguments.get("subject") or self.settings.integrations.followup_email_default_subject),
                        body=str(arguments.get("body") or self.settings.integrations.followup_email_default_body),
                    ),
                    timeout=timeout_secs,
                )
            else:
                result = {"ok": False, "outcome": "unknown_tool", "message": f"Unknown tool: {tool_name}"}
        except asyncio.TimeoutError:
            result = {
                "ok": False,
                "outcome": "timeout",
                "message": "I can check that and send it over after this.",
            }
        except Exception as exc:
            result = {
                "ok": False,
                "outcome": "failed",
                "message": f"Tool failed safely: {exc.__class__.__name__}",
            }
        duration_ms = round((time.monotonic() - started) * 1000, 1)
        event_name = "tool.call.completed" if result.get("ok") else "tool.call.failed"
        result_metadata = _tool_result_metadata(tool_name, result, caller_phone=self.caller_phone)
        if result.get("outcome") == "confirmation_required":
            self._emit(
                "tool.confirmation.required",
                tool_name=tool_name,
                outcome="confirmation_required",
                duration_ms=duration_ms,
                metadata=result_metadata,
            )
        if tool_name == "confirm_calendar_booking":
            self._emit(
                "tool.confirmation.accepted" if result.get("ok") else "tool.confirmation.rejected",
                tool_name=tool_name,
                outcome=str(result.get("outcome") or "unknown"),
                duration_ms=duration_ms,
                metadata=result_metadata,
            )
        if tool_name == "cancel_calendar_booking":
            self._emit(
                "tool.confirmation.accepted" if result.get("ok") else "tool.confirmation.rejected",
                tool_name=tool_name,
                outcome=str(result.get("outcome") or "unknown"),
                duration_ms=duration_ms,
                metadata=result_metadata,
            )
        self._emit(
            event_name,
            tool_name=tool_name,
            outcome=str(result.get("outcome") or ("ok" if result.get("ok") else "failed")),
            duration_ms=duration_ms,
            metadata=result_metadata,
        )
        return result

    def _emit(
        self,
        event_name: str,
        *,
        tool_name: str,
        outcome: str,
        duration_ms: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "client_id": self.client_id,
            "tool_name": tool_name,
            **_tool_integration_metadata(self.settings, tool_name),
            "outcome": outcome,
            **(metadata or {}),
        }
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        self.recorder.emit(event_name, provider="tool", metadata=payload)


def configure_scheduling_tools(settings: Settings, session: Any, recorder: Any, llm: Any, context: Any) -> Any | None:
    client_id = session.client_id or settings.integrations.default_client_id
    enabled_tools = set(getattr(session, "enabled_tools", None) or verbatim_tool_names())
    if not enabled_tools:
        return None
    runtime = SchedulingToolRuntime(
        settings=settings,
        client_id=client_id,
        recorder=recorder,
        caller_phone=getattr(session, "caller_phone", None),
        enabled_tools=enabled_tools,
    )
    return runtime.register(llm, context)


def scheduling_tools_ready(settings: Settings, *, client_id: str) -> bool:
    if not settings.integrations.nango_secret_key:
        return False
    connection = IntegrationStore(settings.integrations.integrations_db_path).get_connection(
        client_id=client_id,
        provider="nango",
        integration_key=settings.integrations.nango_google_calendar_integration_id,
    )
    if not connection or not connection.connection_id:
        return False
    return connection.status.lower() not in {"not_connected", "pending", "failed", "expired"}


def verbatim_tools_ready(settings: Settings, *, client_id: str) -> bool:
    return scheduling_tools_ready(settings, client_id=client_id) or followup_tools_ready(settings)


def create_tool_gate_processor(settings: Settings, session: Any, recorder: Any, tools_schema: Any | None):
    from pipecat.frames.frames import LLMContextFrame
    from pipecat.processors.aggregators.llm_context import NOT_GIVEN
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    client_id = session.client_id or settings.integrations.default_client_id
    enabled_tools = set(getattr(session, "enabled_tools", None) or verbatim_tool_names())

    class ToolGateProcessor(FrameProcessor):
        def __init__(self) -> None:
            super().__init__(name="verbatim-tool-gate")

        async def process_frame(self, frame, direction: FrameDirection):
            await super().process_frame(frame, direction)
            if isinstance(frame, LLMContextFrame):
                text = recorder.latest_user_text or ""
                active = bool(
                    settings.providers.llm_provider != "groq"
                    and tools_schema
                    and _looks_like_tool_turn(text)
                    and verbatim_tools_ready(settings, client_id=client_id)
                    and bool(enabled_tools)
                )
                if active:
                    frame.context.set_tools(tools_schema)
                    frame.context.set_tool_choice("auto")
                    recorder.emit(
                        "tool.schema.activated",
                        provider="tool",
                        metadata={
                            "client_id": client_id,
                            "integration_provider": "verbatim",
                            "integration_key": "safe-tool-surface",
                            "text_preview": text[:160],
                        },
                        once_per_turn=True,
                    )
                else:
                    frame.context.set_tools(NOT_GIVEN)
                    frame.context.set_tool_choice(NOT_GIVEN)
            await self.push_frame(frame, direction)

    return ToolGateProcessor()


def create_calendar_action_processor(settings: Settings, session: Any, recorder: Any):
    from pipecat.frames.frames import LLMContextFrame, LLMFullResponseEndFrame, LLMFullResponseStartFrame, LLMTextFrame
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    client_id = session.client_id or settings.integrations.default_client_id
    enabled_tools = set(getattr(session, "enabled_tools", None) or verbatim_tool_names())
    runtime = SchedulingToolRuntime(
        settings=settings,
        client_id=client_id,
        recorder=recorder,
        caller_phone=getattr(session, "caller_phone", None),
        enabled_tools=enabled_tools,
    )
    handled_turns: set[str] = set()

    class CalendarActionProcessor(FrameProcessor):
        def __init__(self) -> None:
            super().__init__(name="verbatim-calendar-action")
            self.booked_signatures: set[str] = set()
            self.last_booking_response: str | None = None
            self.last_booking_id: str | None = None
            self.last_suggested_action: dict[str, Any] | None = None
            self.pending_sms_body: str | None = None
            self.last_sms_response: str | None = None
            self.awaiting_sms_offer_response = False

        async def process_frame(self, frame, direction: FrameDirection):
            await super().process_frame(frame, direction)
            if not isinstance(frame, LLMContextFrame) or not session.tools_enabled or not enabled_tools:
                await self.push_frame(frame, direction)
                return

            turn_id = recorder.current_turn_id
            if turn_id and turn_id in handled_turns:
                await self.push_frame(frame, direction)
                return

            latest_text = recorder.latest_user_text or ""
            recent_user_texts = getattr(recorder, "recent_user_texts", [])
            recent_text = " ".join(recent_user_texts[-8:])
            recent_tail = " ".join(recent_user_texts[-3:])
            sms_result = await self._handle_sms_followup_turn(
                latest_text=latest_text,
                recent_tail=recent_tail,
                direction=direction,
            )
            if sms_result:
                if turn_id:
                    handled_turns.add(turn_id)
                return

            status_response = _booking_status_response(
                latest_text,
                last_booking_response=self.last_booking_response,
                last_suggested_action=self.last_suggested_action,
            )
            if status_response:
                if turn_id:
                    handled_turns.add(turn_id)
                recorder.emit(
                    "tool.direct.skipped",
                    provider="tool",
                    metadata={
                        "client_id": client_id,
                        "outcome": "booking_already_closed",
                        "text_preview": latest_text[:160],
                    },
                    once_per_turn=True,
                )
                await self._push_response(status_response, direction)
                return

            if self.last_booking_response and not _has_post_booking_tool_intent(latest_text):
                await self.push_frame(frame, direction)
                return

            tool_latest_text = latest_text
            if self.last_suggested_action and _accepts_suggested_slot(latest_text, recent_tail=recent_tail):
                action = _copy_calendar_action(self.last_suggested_action)
                if not _is_explicit_booking_confirmation(latest_text):
                    tool_latest_text = f"{latest_text} yes"
            else:
                action = _calendar_action_from_text(latest_text=latest_text, recent_text=recent_text)
            if not action:
                await self.push_frame(frame, direction)
                return
            if action["tool_name"] not in enabled_tools and action["tool_name"] != "prepare_and_confirm_calendar_booking":
                if _is_calendar_action(action):
                    await self._push_unavailable_calendar_response(action=action, latest_text=latest_text, direction=direction)
                    if turn_id:
                        handled_turns.add(turn_id)
                    return
                await self.push_frame(frame, direction)
                return
            if action["tool_name"] == "prepare_and_confirm_calendar_booking" and not set(scheduling_tool_names()).issubset(enabled_tools):
                await self._push_unavailable_calendar_response(action=action, latest_text=latest_text, direction=direction)
                if turn_id:
                    handled_turns.add(turn_id)
                return
            if not scheduling_tools_ready(settings, client_id=client_id):
                if turn_id:
                    handled_turns.add(turn_id)
                recorder.emit(
                    "tool.direct.skipped",
                    provider="tool",
                    metadata={
                        "client_id": client_id,
                        "outcome": "missing_connection",
                        "tool_name": action["tool_name"],
                        "text_preview": latest_text[:160],
                    },
                    once_per_turn=True,
                )
                await self._push_response("Your calendar is not connected yet.", direction)
                return
            if action.get("arguments", {}).get("missing_details"):
                if turn_id:
                    handled_turns.add(turn_id)
                recorder.emit(
                    "tool.direct.skipped",
                    provider="tool",
                    metadata={
                        "client_id": client_id,
                        **_tool_integration_metadata(settings, action["tool_name"]),
                        "tool_name": action["tool_name"],
                        "outcome": "missing_booking_details",
                        "calendar_checked": False,
                        "booking_booked": False,
                        "text_preview": latest_text[:160],
                    },
                    once_per_turn=True,
                )
                await self._push_response(_calendar_response_text(action, {"ok": False, "outcome": "missing_booking_details"}), direction)
                return
            if action["tool_name"] == "cancel_calendar_booking" and self.last_booking_id:
                action["arguments"]["booking_id"] = self.last_booking_id

            signature = _calendar_action_signature(action)
            if signature and signature in self.booked_signatures:
                if turn_id:
                    handled_turns.add(turn_id)
                response_text = _duplicate_booking_response(action)
                recorder.emit(
                    "tool.direct.skipped",
                    provider="tool",
                    metadata={
                        "client_id": client_id,
                        "outcome": "duplicate_booking_prevented",
                        "tool_name": action["tool_name"],
                        "text_preview": latest_text[:160],
                    },
                    once_per_turn=True,
                )
                await self._push_response(response_text, direction)
                return

            if turn_id:
                handled_turns.add(turn_id)
            recorder.emit(
                "tool.direct.activated",
                provider="tool",
                metadata={
                    "client_id": client_id,
                    **_tool_integration_metadata(settings, action["tool_name"]),
                    "tool_name": action["tool_name"],
                    "text_preview": latest_text[:160],
                    "direct_tool": True,
                },
                once_per_turn=True,
            )
            result = await _run_calendar_action(runtime, action, latest_text=tool_latest_text)
            response_text = _calendar_response_text(action, result)
            suggested_action = _suggested_booking_action(result)
            if suggested_action:
                self.last_suggested_action = suggested_action
            elif action["tool_name"] == "prepare_and_confirm_calendar_booking" and result.get("outcome") == "confirmation_required":
                self.last_suggested_action = _copy_calendar_action(action)
            if signature and result.get("ok") and result.get("outcome") == "booking_confirmed":
                self.booked_signatures.add(signature)
                booking_response = response_text
                self.last_booking_response = booking_response
                booking = result.get("booking") or {}
                self.last_booking_id = str(booking.get("id") or "") or self.last_booking_id
                self.last_suggested_action = None
                self.pending_sms_body = _booking_sms_body(result, fallback=booking_response)
                if runtime.caller_phone:
                    self.awaiting_sms_offer_response = True
                    response_text = f"{booking_response} Want me to text you the viewing confirmation?"
                else:
                    self.pending_sms_body = None
            if result.get("ok") and result.get("outcome") == "booking_cancelled":
                self.last_booking_response = None
                self.last_booking_id = None
                self.last_suggested_action = None
                self.pending_sms_body = None
                self.last_sms_response = None
                self.awaiting_sms_offer_response = False
            await self._push_response(response_text, direction)

        async def _push_response(self, response_text: str, direction: FrameDirection) -> None:
            recorder.emit(
                "transcript.assistant",
                provider="tool",
                metadata={"text": response_text, "source": "calendar_direct"},
            )
            await self.push_frame(LLMFullResponseStartFrame(), direction)
            await self.push_frame(LLMTextFrame(response_text), direction)
            await self.push_frame(LLMFullResponseEndFrame(), direction)

        async def _handle_sms_followup_turn(self, *, latest_text: str, recent_tail: str, direction: FrameDirection) -> bool:
            wants_sms = _asks_for_sms_followup(latest_text)
            asks_sms_status = _asks_sms_status(latest_text)
            if asks_sms_status and self.last_sms_response:
                await self._push_response(self.last_sms_response, direction)
                return True
            if "send_sms_followup" not in enabled_tools:
                if wants_sms or asks_sms_status:
                    recorder.emit(
                        "tool.direct.skipped",
                        provider="tool",
                        metadata={
                            "client_id": client_id,
                            **_tool_integration_metadata(settings, "send_sms_followup"),
                            "tool_name": "send_sms_followup",
                            "outcome": "sms_not_ready",
                            "sms_sent": False,
                            "text_preview": latest_text[:160],
                        },
                        once_per_turn=True,
                    )
                    await self._push_response("SMS is not configured yet.", direction)
                    return True
                return False
            sms_body = self.pending_sms_body or self.last_booking_response or settings.integrations.followup_sms_default_body
            if self.pending_sms_body and self.awaiting_sms_offer_response:
                if _rejects_confirmation(latest_text):
                    self.pending_sms_body = None
                    self.awaiting_sms_offer_response = False
                    await self._push_response("No problem.", direction)
                    return True
                if _is_explicit_booking_confirmation(latest_text) or wants_sms:
                    await self._send_sms_confirmation(sms_body=self.pending_sms_body or sms_body, latest_text=latest_text, direction=direction)
                    return True
                return False
            if wants_sms or asks_sms_status:
                if not self.pending_sms_body and not self.last_booking_response:
                    recorder.emit(
                        "tool.direct.skipped",
                        provider="tool",
                        metadata={
                            "client_id": client_id,
                            **_tool_integration_metadata(settings, "send_sms_followup"),
                            "tool_name": "send_sms_followup",
                            "outcome": "missing_confirmed_booking",
                            "sms_sent": False,
                            "to_phone": runtime.caller_phone,
                            "text_preview": latest_text[:160],
                        },
                        once_per_turn=True,
                    )
                    await self._push_response("I have not sent one yet because the viewing is not booked.", direction)
                    return True
                await self._send_sms_confirmation(sms_body=sms_body, latest_text=latest_text, direction=direction)
                return True
            return False

        async def _push_unavailable_calendar_response(self, *, action: dict[str, Any], latest_text: str, direction: FrameDirection) -> None:
            metadata = {
                "client_id": client_id,
                **_tool_integration_metadata(settings, action["tool_name"]),
                "tool_name": action["tool_name"],
                "outcome": "calendar_not_ready",
                "calendar_checked": False,
                "booking_booked": False,
                "text_preview": latest_text[:160],
            }
            recorder.emit("tool.direct.skipped", provider="tool", metadata=metadata, once_per_turn=True)
            if action["tool_name"] == "prepare_and_confirm_calendar_booking":
                await self._push_response("I cannot book it yet because Google Calendar is not connected.", direction)
            else:
                await self._push_response("I cannot check the calendar yet because Google Calendar is not connected.", direction)

        async def _send_sms_confirmation(self, *, sms_body: str, latest_text: str, direction: FrameDirection) -> None:
            action = {
                "tool_name": "send_sms_followup",
                "arguments": {
                    "body": sms_body,
                    "channel": "sms",
                },
            }
            recorder.emit(
                "tool.direct.activated",
                provider="tool",
                metadata={
                    "client_id": client_id,
                    **_tool_integration_metadata(settings, "send_sms_followup"),
                    "tool_name": "send_sms_followup",
                    "caller_phone_configured": bool(runtime.caller_phone),
                    "direct_tool": True,
                    "text_preview": latest_text[:160],
                },
                once_per_turn=True,
            )
            result = await _run_followup_action(runtime, action)
            response_text = _followup_response_text(action, result)
            if result.get("ok"):
                self.pending_sms_body = None
                self.awaiting_sms_offer_response = False
                self.last_sms_response = "Yes, I sent the viewing confirmation."
            await self._push_response(response_text, direction)

    return CalendarActionProcessor()


def _looks_like_scheduling_turn(text: str) -> bool:
    lowered = text.lower()
    return bool(
        re.search(
            r"\b(calendar|available|availability|slot|schedule|viewing|appointment|book|booking|meet|tomorrow|today|time)\b",
            lowered,
        )
    )


def _looks_like_tool_turn(text: str) -> bool:
    lowered = text.lower()
    return _looks_like_scheduling_turn(lowered) or _asks_for_sms_followup(lowered)


async def _run_calendar_action(runtime: SchedulingToolRuntime, action: dict[str, Any], *, latest_text: str) -> dict[str, Any]:
    if action["tool_name"] == "check_calendar_availability":
        return await runtime.run_tool("check_calendar_availability", action["arguments"])
    if action["tool_name"] == "check_calendar_conflict":
        return await runtime.run_tool("check_calendar_conflict", action["arguments"])
    if action["tool_name"] == "prepare_and_confirm_calendar_booking":
        prepared = await runtime.run_tool("prepare_calendar_booking", action["arguments"])
        if not prepared.get("ok"):
            return prepared
        return await runtime.run_tool(
            "confirm_calendar_booking",
            {
                "pending_booking_id": prepared.get("pending_booking_id"),
                "confirmation_text": latest_text,
            },
        )
    if action["tool_name"] == "cancel_calendar_booking":
        return await runtime.run_tool(
            "cancel_calendar_booking",
            {
                **action["arguments"],
                "confirmation_text": latest_text,
            },
        )
    return {"ok": False, "outcome": "unknown_action", "message": "I can help with calendar bookings."}


async def _run_followup_action(runtime: SchedulingToolRuntime, action: dict[str, Any]) -> dict[str, Any]:
    if action["tool_name"] == "send_sms_followup":
        return await runtime.run_tool("send_sms_followup", action["arguments"])
    if action["tool_name"] == "send_email_followup":
        return await runtime.run_tool("send_email_followup", action["arguments"])
    return {"ok": False, "outcome": "unknown_followup_action", "message": "I can help send a follow-up."}


def _calendar_action_from_text(*, latest_text: str, recent_text: str) -> dict[str, Any] | None:
    latest = _normalize_stuttered_words(latest_text.lower())
    combined = _normalize_stuttered_words(recent_text.strip())
    lowered = combined.lower()
    if _asks_to_cancel_calendar(latest):
        return {
            "tool_name": "cancel_calendar_booking",
            "arguments": {},
        }
    if _asks_booking_status(latest) and not _asks_to_create_booking(latest):
        return None
    recent_has_booking_context = _asks_to_create_booking(lowered) or bool(re.search(r"\b(viewing|appointment|property tour)\b", lowered))
    latest_supplies_time = _has_time(latest) or _extract_date(latest, datetime.now(ZoneInfo("Europe/Paris"))) is not None
    should_book = (
        _asks_to_create_booking(latest)
        or (recent_has_booking_context and latest_supplies_time)
        or (_is_explicit_booking_confirmation(latest) and recent_has_booking_context and _has_time(lowered))
    )
    if should_book and _asks_to_create_booking(latest):
        date_time = _extract_calendar_datetime(combined)
        if not date_time:
            missing_args = _missing_calendar_details(combined)
            return {
                "tool_name": "prepare_and_confirm_calendar_booking",
                "arguments": {"missing_details": True, **missing_args},
            }
        return {
            "tool_name": "prepare_and_confirm_calendar_booking",
            "arguments": {
                "start_iso": date_time["start_iso"],
                "end_iso": date_time["end_iso"],
                "timezone": date_time["timezone"],
                "title": "Property viewing",
                "notes": "Booked by Verbatim voice agent after caller request.",
            },
        }
    if _asks_for_calendar_conflict(latest) or (
        latest_supplies_time
        and _looks_like_slot_continuation(latest)
        and _asks_for_calendar_conflict(lowered)
    ) or (
        _references_previous_calendar_slot(latest)
        and _has_time(lowered)
    ):
        date_time = _extract_calendar_datetime(combined)
        if date_time:
            return {
                "tool_name": "check_calendar_conflict",
                "arguments": {
                    "start_iso": date_time["start_iso"],
                    "end_iso": date_time["end_iso"],
                    "timezone": date_time["timezone"],
                },
            }
        missing_args = _missing_calendar_details(combined)
        return {
            "tool_name": "check_calendar_conflict",
            "arguments": {"missing_details": True, **missing_args},
        }
    if _is_booking_status_or_closing(latest) and not _asks_to_create_booking(latest):
        return None
    if _asks_for_unsupported_calendar_read(latest):
        return {
            "tool_name": "unsupported_calendar_read",
            "arguments": {},
        }
    if _asks_for_availability(latest):
        date_time = _extract_calendar_datetime(combined)
        return {
            "tool_name": "check_calendar_availability",
            "arguments": {
                "date_iso": date_time["date_iso"] if date_time else None,
                "timezone": "Europe/Paris",
                "duration_minutes": 30,
            },
        }
    if should_book:
        date_time = _extract_calendar_datetime(combined)
        if not date_time:
            missing_args = _missing_calendar_details(combined)
            return {
                "tool_name": "prepare_and_confirm_calendar_booking",
                "arguments": {"missing_details": True, **missing_args},
            }
        return {
            "tool_name": "prepare_and_confirm_calendar_booking",
            "arguments": {
                "start_iso": date_time["start_iso"],
                "end_iso": date_time["end_iso"],
                "timezone": date_time["timezone"],
                "title": "Property viewing",
                "notes": "Booked by Verbatim voice agent after caller request.",
            },
        }
    return None


def _followup_action_from_text(
    *,
    latest_text: str,
    recent_text: str,
    default_phone: str | None,
    default_email: str | None,
    sms_body: str,
    email_subject: str,
    email_body: str,
) -> dict[str, Any] | None:
    latest = latest_text.lower()
    combined = f"{recent_text} {latest_text}".strip()
    lowered = combined.lower()
    if _asks_to_book(latest) or _asks_to_cancel_calendar(latest):
        return None
    if _asks_for_sms_followup(lowered):
        return {
            "tool_name": "send_sms_followup",
            "arguments": {
                "body": sms_body,
                "channel": "sms",
            },
        }
    if re.search(r"\b(send|text|message)\b", latest) and re.search(r"\b(details|options|confirmation|follow.?up)\b", latest):
        return {
            "tool_name": "send_sms_followup",
            "arguments": {"body": sms_body, "channel": "sms"},
        }
    return None


def _calendar_response_text(action: dict[str, Any], result: dict[str, Any]) -> str:
    if action["tool_name"] == "unsupported_calendar_read":
        return "I can check a specific time, but I cannot read your full calendar aloud."
    if action.get("arguments", {}).get("missing_details"):
        if action.get("arguments", {}).get("missing_time"):
            return "What time should I use?"
        if action.get("arguments", {}).get("missing_day"):
            return "What day should I use?"
        if action["tool_name"] == "check_calendar_conflict":
            return "What day and time should I check?"
        return "What day and time should I use?"
    if result.get("ok") and result.get("outcome") == "calendar_conflict_checked":
        if result.get("has_conflict"):
            return _busy_with_suggestion(result)
        checked_slot = result.get("checked_slot") or {}
        start = _friendly_datetime(str(checked_slot.get("start_iso") or ""))
        if start != "that time":
            return f"Yes, {start} is open. Should I book the viewing?"
        return "Yes, that time is open. Should I book the viewing?"
    if result.get("ok") and result.get("outcome") == "booking_confirmed":
        booking = result.get("booking") or {}
        start = _friendly_datetime(str(booking.get("start_iso") or ""))
        return f"Done, I booked the viewing for {start}."
    if result.get("ok") and result.get("outcome") == "booking_cancelled":
        return "Done, I removed it from your calendar."
    if result.get("ok") and result.get("outcome") == "available_slots":
        slots = result.get("slots") or []
        if not slots:
            return "I do not see an open slot there."
        first = _friendly_datetime(str(slots[0].get("start_iso") or ""))
        return f"I can do {first} for a viewing. Should I book it?"
    outcome = str(result.get("outcome") or "")
    if outcome == "missing_connection":
        return "Your calendar is not connected yet."
    if outcome == "confirmation_required":
        return "Just to confirm, should I book that viewing?"
    if outcome == "cancellation_confirmation_required":
        return "Just to confirm, should I remove it?"
    if outcome == "slot_conflict":
        return _busy_with_suggestion(result, prefix="That time is already booked, so I did not book it.")
    if outcome == "timeout":
        return "The calendar tool timed out, so I did not book it."
    if outcome == "missing_confirmed_booking":
        return "I do not have a confirmed booking here to remove."
    if outcome == "calendar_cancel_failed":
        return "I could not remove it yet."
    return str(result.get("message") or "I could not book that yet.")[:180]


def _followup_response_text(action: dict[str, Any], result: dict[str, Any]) -> str:
    outcome = str(result.get("outcome") or "")
    if result.get("ok"):
        if outcome == "email_sent":
            return "Done, I sent the email."
        return "Done, I sent the viewing confirmation."
    if outcome in {"missing_phone_destination", "missing_email_destination"}:
        return str(result.get("message") or "Where should I send it?")
    if outcome == "missing_twilio_sms_config":
        return "SMS is not configured yet."
    if outcome == "missing_resend_config":
        return "Email is not configured yet."
    return str(result.get("message") or "I could not send that yet.")[:180]


def _calendar_action_signature(action: dict[str, Any]) -> str | None:
    if action.get("tool_name") != "prepare_and_confirm_calendar_booking":
        return None
    arguments = action.get("arguments") or {}
    start_iso = arguments.get("start_iso")
    end_iso = arguments.get("end_iso")
    if not start_iso or not end_iso:
        return None
    title = str(arguments.get("title") or "Property viewing").strip().lower()
    return f"{start_iso}|{end_iso}|{title}"


def _duplicate_booking_response(action: dict[str, Any]) -> str:
    start = _friendly_datetime(str((action.get("arguments") or {}).get("start_iso") or ""))
    return f"It is already booked for {start}."


def _copy_calendar_action(action: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool_name": str(action.get("tool_name") or ""),
        "arguments": dict(action.get("arguments") or {}),
    }


def _is_calendar_action(action: dict[str, Any]) -> bool:
    return str(action.get("tool_name") or "") in set(scheduling_tool_names()) | {
        "prepare_and_confirm_calendar_booking",
        "unsupported_calendar_read",
    }


def _suggested_booking_action(result: dict[str, Any]) -> dict[str, Any] | None:
    slots = []
    if result.get("outcome") == "calendar_conflict_checked" and not result.get("has_conflict"):
        checked_slot = result.get("checked_slot")
        slots = [checked_slot] if checked_slot else []
    if not slots:
        slots = result.get("suggested_slots") or []
    if not slots and result.get("outcome") == "available_slots":
        slots = result.get("slots") or []
    if not slots:
        return None
    first = slots[0] or {}
    start_iso = str(first.get("start_iso") or "")
    end_iso = str(first.get("end_iso") or "")
    if not start_iso:
        return None
    if not end_iso:
        try:
            start = datetime.fromisoformat(start_iso)
        except ValueError:
            return None
        end_iso = (start + timedelta(minutes=30)).isoformat()
    return {
        "tool_name": "prepare_and_confirm_calendar_booking",
        "arguments": {
            "start_iso": start_iso,
            "end_iso": end_iso,
            "timezone": str(first.get("timezone") or "Europe/Paris"),
            "title": "Property viewing",
            "notes": "Booked by Verbatim voice agent after caller accepted a suggested slot.",
        },
    }


def _busy_with_suggestion(result: dict[str, Any], *, prefix: str = "That time is already booked.") -> str:
    slots = result.get("suggested_slots") or []
    if slots:
        first = _friendly_datetime(str(slots[0].get("start_iso") or ""))
        return f"{prefix} I can do {first} instead."
    return f"{prefix} I do not see another open slot right after it."


def _booking_status_response(
    text: str,
    *,
    last_booking_response: str | None,
    last_suggested_action: dict[str, Any] | None,
) -> str | None:
    lowered = text.lower()
    if _has_unrelated_followup_question(lowered):
        return None
    if _asks_to_create_booking(lowered):
        return None
    if not _is_booking_status_or_closing(lowered):
        return None
    if _asks_booking_status(lowered):
        if last_booking_response:
            return "Yes, it is already booked."
        if last_suggested_action:
            start = _friendly_datetime(str((last_suggested_action.get("arguments") or {}).get("start_iso") or ""))
            return f"Not yet. I can book {start} if that works."
        return "Not yet."
    if not last_booking_response:
        return None
    if re.search(r"\b(already booked|you booked)\b", lowered):
        return "Yes, it is already booked."
    return "You are all set. Have a great day."


def _has_post_booking_tool_intent(text: str) -> bool:
    lowered = text.lower()
    return bool(
        _asks_booking_status(lowered)
        or _asks_for_sms_followup(lowered)
        or _asks_sms_status(lowered)
        or _asks_to_cancel_calendar(lowered)
        or _asks_to_create_booking(lowered)
        or _asks_for_calendar_conflict(lowered)
        or _asks_for_availability(lowered)
    )


def _has_unrelated_followup_question(text: str) -> bool:
    return bool(re.search(r"\b(by the way|also|actually)\b.*\b(what|when|where|why|how|can|could|do|does|is|are)\b", text))


def _is_booking_status_or_closing(text: str) -> bool:
    return bool(
        re.search(
            r"\b(already booked|you booked|did you book|is it booked|what about (?:the )?booking|"
            r"booking (?:doesn'?t|does not|didn'?t|did not) seem|is it on (?:the )?(?:google )?calendar|"
            r"on (?:the )?(?:google )?calendar|thank you|thanks|have a great day|bye|goodbye|that'?s all)\b",
            text,
        )
    )


def _asks_booking_status(text: str) -> bool:
    return bool(
        re.search(
            r"\b(did you book|is it booked|did that book|did it go through|was it booked|what about (?:the )?booking|"
            r"booking (?:doesn'?t|does not|didn'?t|did not) seem|is it on (?:the )?(?:google )?calendar|"
            r"on (?:the )?(?:google )?calendar)\b",
            text,
        )
    )


def _asks_for_sms_followup(text: str) -> bool:
    lowered = text.lower()
    return bool(
        re.search(
            r"\b(text me|send (?:me )?(?:a )?(?:text|sms|message)|send it by text|message me|"
            r"send (?:me )?(?:the )?(?:confirmation|details|options)|confirmation text)\b",
            lowered,
        )
    )


def _asks_sms_status(text: str) -> bool:
    lowered = text.lower()
    return bool(
        re.search(
            r"\b(did you send|have you sent|was it sent|is it sent|i (?:still )?haven'?t received|"
            r"i have not received|confirmation message|confirmation sms|confirmation text)\b",
            lowered,
        )
    )


def _rejects_confirmation(text: str) -> bool:
    return bool(re.search(r"\b(no|nope|not that|wrong|incorrect|hold on|wait|don'?t|do not|cancel)\b", text.lower()))


def _accepts_suggested_slot(text: str, *, recent_tail: str = "") -> bool:
    combined = f"{recent_tail} {text}".lower()
    if re.search(r"\b(no|nope|not yet|wait|hold on|don'?t|do not|wrong|cancel)\b", combined):
        return False
    return bool(
        re.search(
            r"\b(that works|works for me|sounds good|let'?s do it|do it|book it|yes|yeah|yep|ok|okay|"
            r"sure|absolutely|great|amazing|perfect|wonderful|fine|that'?s fine|the one you (?:just )?suggested|that one)\b",
            combined,
        )
    )


def _is_explicit_booking_confirmation(text: str) -> bool:
    lowered = text.lower()
    return bool(
        re.search(
            r"\b(yes|yeah|yep|ok|okay|correct|confirm|go ahead|please do|book that|book it|that works|"
            r"works for me|let'?s do it|do it|sure|absolutely|great|amazing|perfect|wonderful)\b",
            lowered,
        )
    )


def _asks_to_cancel_calendar(text: str) -> bool:
    return bool(re.search(r"\b(delete|remove|cancel|clear|take it off)\b", text)) and bool(
        re.search(r"\b(it|booking|appointment|meeting|viewing|calendar|event)\b", text)
    )


def _asks_for_calendar_conflict(text: str) -> bool:
    has_exact_time = _has_time(text)
    if has_exact_time and re.search(r"\b(available|availability|free|open|busy|conflict)\b", text):
        return True
    return bool(has_exact_time) and bool(
        re.search(
            r"\b(am i free|are (?:you|you guys|we) (?:free|busy|available|open)|"
            r"do i have|have another|anything (?:in|on) my calendar|already have|conflict|"
            r"available at|free at|busy at|open at|can (?:you|we) do|"
            r"could (?:we|you) do|can (?:we|you) make|could (?:we|you) make|"
            r"can i (?:come by|visit|view|see)|could i (?:come by|visit|view|see)|"
            r"can we (?:come by|visit|view|see)|could we (?:come by|visit|view|see)|"
            r"come by|view it)\b",
            text,
        )
    )


def _references_previous_calendar_slot(text: str) -> bool:
    return bool(
        re.search(
            r"\b(that moment|that time|same time|another event|anything (?:in|on) my calendar|already have|conflict)\b",
            text,
        )
    )


def _asks_to_book(text: str) -> bool:
    return bool(re.search(r"\b(book|schedule|set up|put|add|create)\b", text)) and bool(
        re.search(r"\b(calendar|appointment|meeting|viewing|slot|it|that)\b", text)
    )


def _asks_to_create_booking(text: str) -> bool:
    if not _asks_to_book(text):
        return False
    return not bool(
        re.search(
            r"\b(did you book|is it booked|was it booked|did that book|what about (?:the )?booking|"
            r"booking (?:doesn'?t|does not|didn'?t|did not) seem)\b",
            text,
        )
    )


def _asks_for_availability(text: str) -> bool:
    return bool(re.search(r"\b(check|see|look|available|availability|free|open)\b", text)) and bool(
        re.search(r"\b(calendar|slot|time|availability)\b", text)
    )


def _asks_for_unsupported_calendar_read(text: str) -> bool:
    return bool(re.search(r"\b(next|upcoming|what.*calendar|calendar.*have|events?)\b", text)) and not _asks_to_book(text)


def _extract_calendar_datetime(text: str) -> dict[str, str] | None:
    timezone = "Europe/Paris"
    tz = ZoneInfo(timezone)
    now = datetime.now(tz)
    date_value = _extract_date(text, now)
    time_value = _extract_time(text)
    if not date_value or not time_value:
        return None
    start = date_value.replace(hour=time_value[0], minute=time_value[1], second=0, microsecond=0)
    end = start + timedelta(minutes=30)
    return {
        "timezone": timezone,
        "date_iso": start.date().isoformat(),
        "start_iso": start.isoformat(),
        "end_iso": end.isoformat(),
    }


def _missing_calendar_details(text: str) -> dict[str, bool]:
    now = datetime.now(ZoneInfo("Europe/Paris"))
    has_date = _extract_date(text, now) is not None
    has_time = _extract_time(text) is not None
    details: dict[str, bool] = {}
    if has_date and not has_time:
        details["missing_time"] = True
    if has_time and not has_date:
        details["missing_day"] = True
    return details


def _extract_date(text: str, now: datetime) -> datetime | None:
    lowered = re.sub(r"[-–—]", " ", text.lower())
    if "today" in lowered:
        return now
    if "tomorrow" in lowered:
        return now + timedelta(days=1)
    day_number = _extract_day_number(lowered)
    month_number = _extract_month_number(lowered)
    if day_number and month_number:
        year = now.year
        try:
            candidate = now.replace(year=year, month=month_number, day=day_number)
        except ValueError:
            return None
        if candidate.date() < now.date():
            candidate = candidate.replace(year=year + 1)
        return candidate
    if day_number:
        try:
            candidate = now.replace(day=day_number)
        except ValueError:
            return None
        if candidate.date() < now.date():
            month = candidate.month + 1
            year = candidate.year
            if month > 12:
                month = 1
                year += 1
            candidate = candidate.replace(year=year, month=month, day=day_number)
        return candidate
    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    for name, index in weekdays.items():
        if re.search(rf"\b{name}\b", lowered):
            delta = (index - now.weekday()) % 7
            return now + timedelta(days=delta or 7)
    return None


def _extract_month_number(text: str) -> int | None:
    months = {
        "january": 1,
        "jan": 1,
        "february": 2,
        "feb": 2,
        "march": 3,
        "mar": 3,
        "april": 4,
        "apr": 4,
        "may": 5,
        "june": 6,
        "jun": 6,
        "july": 7,
        "jul": 7,
        "august": 8,
        "aug": 8,
        "september": 9,
        "sept": 9,
        "sep": 9,
        "october": 10,
        "oct": 10,
        "november": 11,
        "nov": 11,
        "december": 12,
        "dec": 12,
    }
    for name, value in sorted(months.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", text):
            return value
    return None


def _extract_day_number(text: str) -> int | None:
    match = re.search(r"\b([12]?\d|3[01])(?:st|nd|rd|th)\b", text)
    if match:
        return int(match.group(1))
    words = {
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
        "sixth": 6,
        "seventh": 7,
        "eighth": 8,
        "ninth": 9,
        "tenth": 10,
        "eleventh": 11,
        "twelfth": 12,
        "thirteenth": 13,
        "fourteenth": 14,
        "fifteenth": 15,
        "sixteenth": 16,
        "seventeenth": 17,
        "eighteenth": 18,
        "nineteenth": 19,
        "twentieth": 20,
        "twenty first": 21,
        "twenty second": 22,
        "twenty third": 23,
        "twenty fourth": 24,
        "twenty fifth": 25,
        "twenty sixth": 26,
        "twenty seventh": 27,
        "twenty eighth": 28,
        "twenty ninth": 29,
        "thirtieth": 30,
        "thirty first": 31,
    }
    for word, value in sorted(words.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"\b{re.escape(word)}\b", text):
            return value
    return None


_SPOKEN_HOURS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
_SPOKEN_HOUR_RE = "|".join(_SPOKEN_HOURS)
_SPOKEN_MINUTES = {
    "oh one": 1,
    "o one": 1,
    "zero one": 1,
    "oh two": 2,
    "o two": 2,
    "zero two": 2,
    "oh three": 3,
    "o three": 3,
    "zero three": 3,
    "oh four": 4,
    "o four": 4,
    "zero four": 4,
    "oh five": 5,
    "o five": 5,
    "zero five": 5,
    "oh six": 6,
    "o six": 6,
    "zero six": 6,
    "oh seven": 7,
    "o seven": 7,
    "zero seven": 7,
    "oh eight": 8,
    "o eight": 8,
    "zero eight": 8,
    "oh nine": 9,
    "o nine": 9,
    "zero nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "twenty one": 21,
    "twenty two": 22,
    "twenty three": 23,
    "twenty four": 24,
    "twenty five": 25,
    "twenty six": 26,
    "twenty seven": 27,
    "twenty eight": 28,
    "twenty nine": 29,
    "thirty": 30,
    "thirty one": 31,
    "thirty two": 32,
    "thirty three": 33,
    "thirty four": 34,
    "thirty five": 35,
    "thirty six": 36,
    "thirty seven": 37,
    "thirty eight": 38,
    "thirty nine": 39,
    "forty": 40,
    "forty one": 41,
    "forty two": 42,
    "forty three": 43,
    "forty four": 44,
    "forty five": 45,
    "forty six": 46,
    "forty seven": 47,
    "forty eight": 48,
    "forty nine": 49,
    "fifty": 50,
    "fifty one": 51,
    "fifty two": 52,
    "fifty three": 53,
    "fifty four": 54,
    "fifty five": 55,
    "fifty six": 56,
    "fifty seven": 57,
    "fifty eight": 58,
    "fifty nine": 59,
}
_SPOKEN_MINUTE_RE = "|".join(sorted((re.escape(key) for key in _SPOKEN_MINUTES), key=len, reverse=True))


def _normalize_meridiem(text: str) -> str:
    lowered = re.sub(r"[-–—]", " ", text.lower())
    lowered = re.sub(r"\ba\s*\.?\s*m\.?\b", "am", lowered)
    lowered = re.sub(r"\bp\s*\.?\s*m\.?\b", "pm", lowered)
    return lowered


def _spoken_minute_value(text: str) -> int | None:
    value = _SPOKEN_MINUTES.get(text.strip())
    return value if value is not None and 0 <= value <= 59 else None


def _extract_time(text: str) -> tuple[int, int] | None:
    lowered = _normalize_meridiem(text)
    match = re.search(r"\b(?:at\s*)?([01]?\d|2[0-3])(?::([0-5]\d))?\s*(am|pm)\b", lowered)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        meridiem = match.group(3)
        if meridiem == "pm" and hour < 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0
        return hour, minute
    word_match = re.search(
        rf"\b(?:at\s*)?({_SPOKEN_HOUR_RE})(?:\s+({_SPOKEN_MINUTE_RE}))?\s*(am|pm)\b",
        lowered,
    )
    if not word_match:
        return None
    hour = _SPOKEN_HOURS[word_match.group(1)]
    minute = _spoken_minute_value(word_match.group(2) or "") or 0
    meridiem = word_match.group(3)
    if meridiem == "pm" and hour < 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    return hour, minute


def _has_time(text: str) -> bool:
    return _extract_time(text) is not None


def _looks_like_slot_continuation(text: str) -> bool:
    lowered = text.lower()
    if len(lowered.split()) > 12:
        return False
    return bool(
        _has_time(lowered)
        or _extract_date(lowered, datetime.now(ZoneInfo("Europe/Paris"))) is not None
        or re.search(r"\b(at|on|instead|that time|this time)\b", lowered)
    )


def _extract_email(text: str) -> str | None:
    match = re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text, re.I)
    return match.group(0) if match else None


_PHONE_DIGIT_WORDS = {
    "zero": "0",
    "oh": "0",
    "o": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
}
_PHONE_TENS_WORDS = {
    "twenty": "2",
    "thirty": "3",
    "forty": "4",
    "fifty": "5",
    "sixty": "6",
    "seventy": "7",
    "eighty": "8",
    "ninety": "9",
}


def _extract_phone(text: str) -> str | None:
    match = re.search(r"(?<!\w)(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,5}\d{2,4}(?!\w)", text)
    if match:
        value = re.sub(r"[^\d+]", "", match.group(0))
        normalized, status = _validate_phone(value)
        return normalized if status == "complete" else None
    fragment, pending_tens = _extract_phone_fragment_parts(text)
    normalized, status = _validate_phone(fragment, has_pending_tens=bool(pending_tens))
    return normalized if status == "complete" else None


def _extract_phone_fragment(text: str) -> str | None:
    fragment, _ = _extract_phone_fragment_parts(text)
    return fragment


def _extract_phone_fragment_parts(text: str) -> tuple[str | None, str | None]:
    lowered = re.sub(r"[-–—]", " ", text.lower())
    lowered = re.sub(r"[^\w+\s]", " ", lowered)
    tokens = [token for token in lowered.split() if token]
    if not tokens:
        return None, None
    pieces: list[str] = []
    has_plus = False
    pending_tens: str | None = None
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "plus":
            if not pieces:
                has_plus = True
            index += 1
            continue
        if token.startswith("+") and re.search(r"\d", token):
            if not pieces:
                has_plus = True
            pieces.append(re.sub(r"\D", "", token))
            index += 1
            continue
        if re.fullmatch(r"\d+", token):
            pieces.append(token)
            index += 1
            continue
        if token in _PHONE_DIGIT_WORDS:
            pieces.append(_PHONE_DIGIT_WORDS[token])
            index += 1
            continue
        if token in _PHONE_TENS_WORDS:
            next_token = tokens[index + 1] if index + 1 < len(tokens) else ""
            if next_token in _PHONE_DIGIT_WORDS and _PHONE_DIGIT_WORDS[next_token] != "0":
                pieces.append(_PHONE_TENS_WORDS[token] + _PHONE_DIGIT_WORDS[next_token])
                index += 2
            elif not pieces and index == len(tokens) - 1:
                pieces.append(_PHONE_TENS_WORDS[token] + "0")
                index += 1
            else:
                pending_tens = _PHONE_TENS_WORDS[token]
                index += 1
            continue
        index += 1
    if not pieces:
        return None, pending_tens
    digits = "".join(pieces)
    return (f"+{digits}" if has_plus else digits), pending_tens


def _merge_phone_fragments(fragments: list[str]) -> str | None:
    if not fragments:
        return None
    has_plus = any(fragment.strip().startswith("+") for fragment in fragments if fragment)
    digits = "".join(re.sub(r"\D", "", fragment) for fragment in fragments if fragment)
    if not digits:
        return None
    return f"+{digits}" if has_plus else digits


def _is_complete_phone(phone: str | None) -> bool:
    _, status = _validate_phone(phone)
    return status == "complete"


def _validate_phone(phone: str | None, *, has_pending_tens: bool = False) -> tuple[str | None, str]:
    if not phone:
        return None, "empty"
    normalized = _normalize_phone(phone)
    digits = re.sub(r"\D", "", normalized)
    if has_pending_tens:
        return normalized, "partial"
    known_profiles = {
        "33": {"total_digits": 11, "mobile_prefixes": {"6", "7"}},
        "1": {"total_digits": 11, "mobile_prefixes": set()},
        "34": {"total_digits": 11, "mobile_prefixes": {"6", "7"}},
        "44": {"total_digits": 12, "mobile_prefixes": {"7"}},
        "971": {"total_digits": 12, "mobile_prefixes": {"5"}},
    }
    if normalized.startswith("+"):
        for code, profile in sorted(known_profiles.items(), key=lambda item: len(item[0]), reverse=True):
            if digits.startswith(code):
                expected = int(profile["total_digits"])
                if len(digits) < expected:
                    return normalized, "partial"
                if len(digits) > expected:
                    return normalized, "overflow"
                prefixes = set(profile["mobile_prefixes"])
                national = digits[len(code) :]
                if prefixes and national and national[0] not in prefixes:
                    return normalized, "invalid"
                return normalized, "complete"
        if len(digits) < 8:
            return normalized, "partial"
        if len(digits) > 15:
            return normalized, "overflow"
        return normalized, "complete"
    if digits.startswith(("06", "07")):
        if len(digits) < 10:
            return normalized, "partial"
        if len(digits) > 10:
            return normalized, "overflow"
        return _normalize_phone(digits), "complete"
    if len(digits) < 10:
        return normalized, "partial"
    if len(digits) > 15:
        return normalized, "overflow"
    return normalized, "complete"


def _normalize_phone(phone: str) -> str:
    stripped = phone.strip()
    digits = re.sub(r"\D", "", stripped)
    if stripped.startswith("+"):
        return f"+{digits}"
    if digits.startswith(("06", "07")) and len(digits) == 10:
        return f"+33{digits[1:]}"
    return digits


def _trusted_caller_phone(phone: str | None) -> str | None:
    normalized, status = _validate_phone(phone)
    return normalized if status == "complete" else None


def _booking_sms_body(result: dict[str, Any], *, fallback: str) -> str:
    booking = result.get("booking") or {}
    start = _friendly_datetime(str(booking.get("start_iso") or ""))
    if start != "that time":
        return f"Your viewing is confirmed for {start}."
    return fallback


def _friendly_datetime(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return "that time"
    return parsed.strftime("%A %B %-d at %-I:%M %p").replace(":00 ", " ")


def _tool_integration_metadata(settings: Settings, tool_name: str) -> dict[str, str]:
    if tool_name == "send_sms_followup":
        return {"integration_provider": "twilio", "integration_key": "twilio-messaging"}
    if tool_name == "send_email_followup":
        return {"integration_provider": "resend", "integration_key": "resend-email"}
    return {
        "integration_provider": "nango",
        "integration_key": settings.integrations.nango_google_calendar_integration_id,
    }


def _tool_result_metadata(tool_name: str, result: dict[str, Any], *, caller_phone: str | None) -> dict[str, Any]:
    outcome = str(result.get("outcome") or "")
    payload: dict[str, Any] = {
        "ok": bool(result.get("ok")),
        "tool_result_outcome": outcome,
    }
    if tool_name in {"check_calendar_availability", "check_calendar_conflict"}:
        payload["calendar_checked"] = bool(result.get("ok"))
        if "has_conflict" in result:
            payload["calendar_has_conflict"] = bool(result.get("has_conflict"))
        checked_slot = result.get("checked_slot") if isinstance(result.get("checked_slot"), dict) else None
        if checked_slot:
            payload["start_iso"] = checked_slot.get("start_iso")
            payload["end_iso"] = checked_slot.get("end_iso")
        if result.get("suggested_slots"):
            payload["suggested_slot_count"] = len(result.get("suggested_slots") or [])
    if tool_name == "prepare_calendar_booking":
        payload["booking_prepared"] = bool(result.get("ok"))
        payload["pending_booking_id"] = result.get("pending_booking_id")
        payload["start_iso"] = result.get("start_iso")
        payload["end_iso"] = result.get("end_iso")
    if tool_name == "confirm_calendar_booking":
        booking = result.get("booking") if isinstance(result.get("booking"), dict) else {}
        payload["booking_booked"] = bool(result.get("ok") and outcome == "booking_confirmed")
        payload["booking_id"] = booking.get("id")
        payload["calendar_event_id"] = booking.get("external_event_id")
        payload["start_iso"] = booking.get("start_iso")
        payload["end_iso"] = booking.get("end_iso")
        if "has_conflict" in result:
            payload["calendar_has_conflict"] = bool(result.get("has_conflict"))
        if result.get("suggested_slots"):
            payload["suggested_slot_count"] = len(result.get("suggested_slots") or [])
    if tool_name == "cancel_calendar_booking":
        payload["booking_cancelled"] = bool(result.get("ok") and outcome == "booking_cancelled")
    if tool_name == "send_sms_followup":
        payload["sms_sent"] = bool(result.get("ok") and outcome in {"sms_sent", "whatsapp_sent"})
        payload["to_phone"] = caller_phone
        payload["destination_preview"] = result.get("destination_preview")
        payload["message_id"] = result.get("message_id")
    if tool_name == "send_email_followup":
        payload["email_sent"] = bool(result.get("ok") and outcome == "email_sent")
        payload["destination_preview"] = result.get("destination_preview")
        payload["message_id"] = result.get("message_id")
    return {key: value for key, value in payload.items() if value not in {None, ""}}


def _normalize_stuttered_words(text: str) -> str:
    previous = None
    current = text
    for _ in range(3):
        previous = current
        current = re.sub(r"\b([a-z0-9]+)\s+\1\b", r"\1", current, flags=re.I)
        if current == previous:
            break
    return current


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
