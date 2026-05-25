import asyncio

import httpx
import respx

from verbatim.config import Settings
from verbatim.integrations.followup import FollowupService, followup_tools_ready
from verbatim.integrations.scheduling import SchedulingService
from verbatim.integrations.store import CALENDAR_TOOL_NAMES, IntegrationStore
from verbatim.integrations.tools import (
    _accepts_suggested_slot,
    _booking_status_response,
    _calendar_action_from_text,
    _asks_sms_status,
    _calendar_response_text,
    _extract_phone,
    _extract_phone_fragment,
    _extract_phone_fragment_parts,
    _extract_time,
    _followup_action_from_text,
    _followup_response_text,
    _merge_phone_fragments,
    _suggested_booking_action,
    _validate_phone,
    SchedulingToolRuntime,
    build_scheduling_tools_schema,
    scheduling_tools_ready,
)


class FakeNango:
    def __init__(self, *, busy=None):
        self.created = []
        self.deleted = []
        self.busy = busy or []

    async def google_calendar_freebusy(self, **kwargs):
        return {"calendars": {"primary": {"busy": self.busy}}}

    async def google_calendar_create_event(self, **kwargs):
        self.created.append(kwargs)
        return {"id": "event_1", "htmlLink": "https://calendar.example/event_1"}

    async def google_calendar_delete_event(self, **kwargs):
        self.deleted.append(kwargs)
        return {}


def test_sqlite_integration_store_crud(tmp_path):
    store = IntegrationStore(tmp_path / "integrations.db")
    connection = store.upsert_connection(
        client_id="client-a",
        provider="nango",
        integration_key="google-calendar",
        connection_id="conn_1",
        status="connected",
        allowed_tools=CALENDAR_TOOL_NAMES,
    )

    assert connection.connection_id == "conn_1"
    assert store.get_connection(client_id="client-a", provider="nango", integration_key="google-calendar")
    assert store.list_connections(client_id="client-a")[0].allowed_tools == CALENDAR_TOOL_NAMES


def test_tool_schema_exposes_only_verbatim_scheduling_tools():
    schema = build_scheduling_tools_schema()
    names = [tool.name for tool in schema.standard_tools]

    assert names == [
        "check_calendar_availability",
        "check_calendar_conflict",
        "prepare_calendar_booking",
        "confirm_calendar_booking",
        "cancel_calendar_booking",
        "send_sms_followup",
    ]


def test_missing_nango_connection_returns_safe_fallback(tmp_path):
    service = SchedulingService(
        store=IntegrationStore(tmp_path / "integrations.db"),
        nango=FakeNango(),
        client_id="client-a",
        integration_key="google-calendar",
    )

    result = asyncio.run(service.check_calendar_availability(date_iso="2026-05-23"))

    assert result["ok"] is False
    assert result["outcome"] == "missing_connection"


def test_booking_requires_explicit_confirmation_and_writes_once(tmp_path):
    store = IntegrationStore(tmp_path / "integrations.db")
    store.upsert_connection(
        client_id="client-a",
        provider="nango",
        integration_key="google-calendar",
        connection_id="conn_1",
        status="connected",
        allowed_tools=CALENDAR_TOOL_NAMES,
    )
    nango = FakeNango()
    service = SchedulingService(
        store=store,
        nango=nango,
        client_id="client-a",
        integration_key="google-calendar",
    )

    prepared = asyncio.run(
        service.prepare_calendar_booking(
            start_iso="2026-05-23T10:00:00+02:00",
            end_iso="2026-05-23T10:30:00+02:00",
        )
    )
    rejected = asyncio.run(
        service.confirm_calendar_booking(
            pending_booking_id=prepared["pending_booking_id"],
            latest_user_text="maybe later",
        )
    )
    confirmed = asyncio.run(
        service.confirm_calendar_booking(
            pending_booking_id=prepared["pending_booking_id"],
            latest_user_text="yes, book it",
        )
    )
    repeated = asyncio.run(
        service.confirm_calendar_booking(
            pending_booking_id=prepared["pending_booking_id"],
            latest_user_text="yes",
        )
    )

    assert prepared["requires_confirmation"] is True
    assert rejected["ok"] is False
    assert confirmed["ok"] is True
    assert repeated["idempotent"] is True
    assert len(nango.created) == 1


def test_booking_accepts_natural_suggested_slot_confirmation(tmp_path):
    store = IntegrationStore(tmp_path / "integrations.db")
    store.upsert_connection(
        client_id="client-a",
        provider="nango",
        integration_key="google-calendar",
        connection_id="conn_1",
        status="connected",
        allowed_tools=CALENDAR_TOOL_NAMES,
    )
    service = SchedulingService(
        store=store,
        nango=FakeNango(),
        client_id="client-a",
        integration_key="google-calendar",
    )

    prepared = asyncio.run(
        service.prepare_calendar_booking(
            start_iso="2026-05-30T09:00:00+02:00",
            end_iso="2026-05-30T09:30:00+02:00",
        )
    )
    confirmed = asyncio.run(
        service.confirm_calendar_booking(
            pending_booking_id=prepared["pending_booking_id"],
            latest_user_text="Okay. Let's do it.",
        )
    )

    assert confirmed["ok"] is True


def test_booking_does_not_write_when_calendar_time_is_busy(tmp_path):
    store = IntegrationStore(tmp_path / "integrations.db")
    store.upsert_connection(
        client_id="client-a",
        provider="nango",
        integration_key="google-calendar",
        connection_id="conn_1",
        status="connected",
        allowed_tools=CALENDAR_TOOL_NAMES,
    )
    nango = FakeNango(
        busy=[
            {
                "start": "2026-05-23T10:00:00+02:00",
                "end": "2026-05-23T10:30:00+02:00",
            }
        ]
    )
    service = SchedulingService(
        store=store,
        nango=nango,
        client_id="client-a",
        integration_key="google-calendar",
    )

    prepared = asyncio.run(
        service.prepare_calendar_booking(
            start_iso="2026-05-23T10:00:00+02:00",
            end_iso="2026-05-23T10:30:00+02:00",
        )
    )
    confirmed = asyncio.run(
        service.confirm_calendar_booking(
            pending_booking_id=prepared["pending_booking_id"],
            latest_user_text="yes, book it",
        )
    )

    assert confirmed["ok"] is False
    assert confirmed["outcome"] == "slot_conflict"
    assert confirmed["suggested_slots"]
    assert len(nango.created) == 0


def test_calendar_tools_ready_accepts_nango_error_status_with_connection_id(tmp_path):
    settings = Settings.from_env(
        {
            "NANGO_SECRET_KEY": "nango-secret",
            "VERBATIM_INTEGRATIONS_DB_PATH": str(tmp_path / "integrations.db"),
        }
    )
    store = IntegrationStore(settings.integrations.integrations_db_path)
    store.upsert_connection(
        client_id="client-a",
        provider="nango",
        integration_key=settings.integrations.nango_google_calendar_integration_id,
        connection_id="calendar_conn",
        status="error",
        allowed_tools=CALENDAR_TOOL_NAMES,
    )

    assert scheduling_tools_ready(settings, client_id="client-a") is True


def test_cancel_confirmed_booking_deletes_once(tmp_path):
    store = IntegrationStore(tmp_path / "integrations.db")
    store.upsert_connection(
        client_id="client-a",
        provider="nango",
        integration_key="google-calendar",
        connection_id="conn_1",
        status="connected",
        allowed_tools=CALENDAR_TOOL_NAMES,
    )
    nango = FakeNango()
    service = SchedulingService(
        store=store,
        nango=nango,
        client_id="client-a",
        integration_key="google-calendar",
    )

    prepared = asyncio.run(
        service.prepare_calendar_booking(
            start_iso="2026-05-23T10:00:00+02:00",
            end_iso="2026-05-23T10:30:00+02:00",
        )
    )
    confirmed = asyncio.run(
        service.confirm_calendar_booking(
            pending_booking_id=prepared["pending_booking_id"],
            latest_user_text="yes, book it",
        )
    )
    cancelled = asyncio.run(
        service.cancel_calendar_booking(
            booking_id=confirmed["booking"]["id"],
            latest_user_text="delete it",
        )
    )
    repeated = asyncio.run(
        service.cancel_calendar_booking(
            booking_id=confirmed["booking"]["id"],
            latest_user_text="delete it",
        )
    )

    assert cancelled["ok"] is True
    assert cancelled["outcome"] == "booking_cancelled"
    assert repeated["idempotent"] is True
    assert len(nango.deleted) == 1


def test_settings_default_tools_on():
    settings = Settings.from_env({})
    assert settings.integrations.tools_enabled is True


def test_followup_tool_config_detection():
    settings = Settings.from_env(
        {
            "TWILIO_ACCOUNT_SID": "AC123",
            "TWILIO_AUTH_TOKEN": "auth",
            "TWILIO_FROM_NUMBER": "+15550000000",
        }
    )

    assert followup_tools_ready(settings) is True


@respx.mock
def test_twilio_sms_followup_sends_without_leaking_secret():
    settings = Settings.from_env(
        {
            "TWILIO_ACCOUNT_SID": "AC123",
            "TWILIO_AUTH_TOKEN": "auth-secret",
            "TWILIO_FROM_NUMBER": "+15550000000",
        }
    )
    route = respx.post("https://api.twilio.com/2010-04-01/Accounts/AC123/Messages.json").mock(
        return_value=httpx.Response(201, json={"sid": "SM123"})
    )

    result = asyncio.run(
        FollowupService(settings=settings, client_id="client-a").send_sms_followup(
            to_phone="+15551112222",
            body="Viewing confirmed.",
        )
    )

    assert result["ok"] is True
    assert result["outcome"] == "sms_sent"
    assert result["destination_preview"] == "***2222"
    assert "auth-secret" not in str(result)
    assert route.called


@respx.mock
def test_sms_tool_uses_simulated_caller_phone_and_ignores_llm_number():
    settings = Settings.from_env(
        {
            "TWILIO_ACCOUNT_SID": "AC123",
            "TWILIO_AUTH_TOKEN": "auth-secret",
            "TWILIO_FROM_NUMBER": "+15550000000",
        }
    )
    route = respx.post("https://api.twilio.com/2010-04-01/Accounts/AC123/Messages.json").mock(
        return_value=httpx.Response(201, json={"sid": "SM123"})
    )

    class Recorder:
        def emit(self, *args, **kwargs):
            return {}

    runtime = SchedulingToolRuntime(
        settings=settings,
        client_id="client-a",
        recorder=Recorder(),
        caller_phone="+33686306987",
    )
    result = asyncio.run(
        runtime.run_tool(
            "send_sms_followup",
            {"to_phone": "+15551112222", "body": "Viewing confirmed.", "channel": "sms"},
        )
    )

    assert result["ok"] is True
    assert result["outcome"] == "sms_sent"
    assert result["destination_preview"] == "***6987"
    assert route.called


@respx.mock
def test_sms_tool_emits_terminal_safe_result_facts():
    settings = Settings.from_env(
        {
            "TWILIO_ACCOUNT_SID": "AC123",
            "TWILIO_AUTH_TOKEN": "auth-secret",
            "TWILIO_FROM_NUMBER": "+15550000000",
        }
    )
    respx.post("https://api.twilio.com/2010-04-01/Accounts/AC123/Messages.json").mock(
        return_value=httpx.Response(201, json={"sid": "SM123"})
    )

    class Recorder:
        def __init__(self):
            self.events = []

        def emit(self, event_name, **kwargs):
            self.events.append({"event_name": event_name, **kwargs})

    recorder = Recorder()
    runtime = SchedulingToolRuntime(
        settings=settings,
        client_id="client-a",
        recorder=recorder,
        caller_phone="+33686306987",
    )

    result = asyncio.run(runtime.run_tool("send_sms_followup", {"body": "Viewing confirmed.", "channel": "sms"}))

    assert result["ok"] is True
    completed = [event for event in recorder.events if event["event_name"] == "tool.call.completed"][-1]
    metadata = completed["metadata"]
    assert metadata["sms_sent"] is True
    assert metadata["to_phone"] == "+33686306987"
    assert metadata["destination_preview"] == "***6987"
    assert "auth-secret" not in str(completed)


@respx.mock
def test_resend_email_followup_sends_without_leaking_secret():
    settings = Settings.from_env(
        {
            "RESEND_API_KEY": "resend-secret",
            "RESEND_FROM_EMAIL": "team@example.com",
        }
    )
    route = respx.post("https://api.resend.com/emails").mock(return_value=httpx.Response(200, json={"id": "email_123"}))

    result = asyncio.run(
        FollowupService(settings=settings, client_id="client-a").send_email_followup(
            to_email="caller@example.com",
            subject="Follow-up",
            body="Details are on the way.",
        )
    )

    assert result["ok"] is True
    assert result["outcome"] == "email_sent"
    assert result["destination_preview"] == "c***@example.com"
    assert "resend-secret" not in str(result)
    assert route.called


def test_followup_action_detects_sms_request_with_phone_number():
    sms_action = _followup_action_from_text(
        latest_text="Can you text me the confirmation at +15551112222?",
        recent_text="Can you text me the confirmation at +15551112222?",
        default_phone=None,
        default_email=None,
        sms_body="Done, I booked it.",
        email_subject="Follow-up",
        email_body="Done, I booked it.",
    )

    assert sms_action
    assert sms_action["tool_name"] == "send_sms_followup"
    assert "to_phone" not in sms_action["arguments"]


def test_spoken_phone_number_fragments_are_parsed_deterministically():
    assert _extract_phone_fragment("My phone number is plus three three six") == "+336"
    assert _extract_phone_fragment("eight six") == "86"
    assert _extract_phone_fragment("three zero") == "30"
    assert _extract_phone_fragment("7.") == "7"
    assert _merge_phone_fragments(["+336", "86", "30", "69", "8", "7"]) == "+33686306987"


def test_spoken_phone_fragment_holds_trailing_tens_until_next_digit():
    fragment, pending = _extract_phone_fragment_parts("Sixty nine eighty")

    assert fragment == "69"
    assert pending == "8"
    assert _merge_phone_fragments(["+336", "86", "30", fragment or "", pending + "7"]) == "+33686306987"


def test_french_phone_validation_is_country_aware():
    assert _validate_phone("+3368630698") == ("+3368630698", "partial")
    assert _validate_phone("+33686306987") == ("+33686306987", "complete")
    assert _validate_phone("+336863069878") == ("+336863069878", "overflow")
    assert _validate_phone("86306987") == ("86306987", "partial")
    assert _validate_phone("0686306987") == ("+33686306987", "complete")


def test_complete_spoken_phone_number_is_parsed_without_llm_memory():
    phone = _extract_phone("My phone number is plus three three six eight six three zero six nine eight seven")

    assert phone == "+33686306987"


def test_followup_action_does_not_use_default_phone_or_email():
    action = _followup_action_from_text(
        latest_text="Can you text me the confirmation?",
        recent_text="Can you text me the confirmation?",
        default_phone="+15551112222",
        default_email="caller@example.com",
        sms_body="Done, I booked it.",
        email_subject="Follow-up",
        email_body="Done, I booked it.",
    )

    assert action
    assert action["tool_name"] == "send_sms_followup"
    assert "to_phone" not in action["arguments"]


def test_sms_followup_response_is_viewing_confirmation():
    response = _followup_response_text(
        {"tool_name": "send_sms_followup", "arguments": {}},
        {"ok": True, "outcome": "sms_sent"},
    )

    assert response == "Done, I sent the viewing confirmation."


def test_followup_action_ignores_email_for_now():
    action = _followup_action_from_text(
        latest_text="Send me an email at caller@example.com.",
        recent_text="Send me an email at caller@example.com.",
        default_phone=None,
        default_email=None,
        sms_body="Details.",
        email_subject="Follow-up",
        email_body="Details.",
    )

    assert action is None


def test_followup_response_asks_for_missing_destination():
    response = _followup_response_text(
        {"tool_name": "send_sms_followup", "arguments": {}},
        {"ok": False, "outcome": "missing_phone_destination", "message": "What phone number should I send it to?"},
    )

    assert response == "What phone number should I send it to?"


def test_calendar_action_combines_split_booking_turns():
    recent_text = (
        "I saw a property and want a viewing Monday on the twenty fifth. "
        "At 2PM. Can you book it on my calendar?"
    )

    action = _calendar_action_from_text(
        latest_text="Can you book it on my calendar?",
        recent_text=recent_text,
    )

    assert action
    assert action["tool_name"] == "prepare_and_confirm_calendar_booking"
    assert action["arguments"]["start_iso"]
    assert "T14:00:00" in action["arguments"]["start_iso"]


def test_calendar_action_parses_flux_spoken_may_date_and_word_time():
    action = _calendar_action_from_text(
        latest_text="Uh, the twenty sixth of June at seven PM.",
        recent_text="Let's book a meeting on the twenty sixth. Uh, the twenty sixth of June at seven PM.",
    )

    assert action
    assert action["tool_name"] == "prepare_and_confirm_calendar_booking"
    assert "2026-06-26T19:00:00" in action["arguments"]["start_iso"]


def test_calendar_action_uses_prior_spoken_date_when_latest_supplies_word_time():
    action = _calendar_action_from_text(
        latest_text="Friday, seven PM.",
        recent_text="Let's book a meeting on the twenty sixth of June. Friday, seven PM.",
    )

    assert action
    assert action["tool_name"] == "prepare_and_confirm_calendar_booking"
    assert "2026-06-26T19:00:00" in action["arguments"]["start_iso"]


def test_spoken_time_parser_handles_word_meridiem():
    assert _extract_time("Friday at seven PM") == (19, 0)
    assert _extract_time("Friday at seven p m") == (19, 0)
    assert _extract_time("Friday at two thirty PM") == (14, 30)


def test_calendar_action_asks_for_missing_booking_details():
    action = _calendar_action_from_text(
        latest_text="Can you book it on my calendar?",
        recent_text="Can you book it on my calendar?",
    )

    assert action
    assert action["tool_name"] == "prepare_and_confirm_calendar_booking"
    assert action["arguments"]["missing_details"] is True


def test_calendar_responses_frame_bookings_as_property_viewings():
    open_response = _calendar_response_text(
        {"tool_name": "check_calendar_conflict", "arguments": {}},
        {
            "ok": True,
            "outcome": "calendar_conflict_checked",
            "has_conflict": False,
            "checked_slot": {"start_iso": "2026-05-23T10:00:00+02:00"},
        },
    )
    booked_response = _calendar_response_text(
        {"tool_name": "confirm_calendar_booking", "arguments": {}},
        {
            "ok": True,
            "outcome": "booking_confirmed",
            "booking": {"start_iso": "2026-05-23T10:00:00+02:00"},
        },
    )

    assert "book the viewing" in open_response
    assert "booked the viewing" in booked_response


def test_calendar_action_catches_book_that_without_details():
    action = _calendar_action_from_text(
        latest_text="Wonderful. Can you book that in?",
        recent_text="Did you find anything? Wonderful. Can you book that in?",
    )

    assert action
    assert action["tool_name"] == "prepare_and_confirm_calendar_booking"
    assert action["arguments"]["missing_details"] is True


def test_calendar_action_uses_recent_booking_context_only_for_date_or_confirmation():
    recent_text = (
        "I need help booking a property viewing. "
        "Friday at 2PM."
    )

    time_action = _calendar_action_from_text(
        latest_text="Friday at 2PM.",
        recent_text=recent_text,
    )
    confirm_action = _calendar_action_from_text(
        latest_text="Yes. Book that in.",
        recent_text=recent_text,
    )

    assert time_action
    assert time_action["tool_name"] == "prepare_and_confirm_calendar_booking"
    assert confirm_action
    assert confirm_action["tool_name"] == "prepare_and_confirm_calendar_booking"


def test_calendar_action_does_not_reuse_stale_booking_context_for_unrelated_turn():
    action = _calendar_action_from_text(
        latest_text="Tool calling abilities are on, Nick.",
        recent_text="I need help booking a property viewing. Friday at 2PM.",
    )

    assert action is None


def test_calendar_action_does_not_rebook_when_user_says_already_booked():
    action = _calendar_action_from_text(
        latest_text="Yeah, you already booked it, thank you.",
        recent_text="I need help booking a property viewing. Friday at 2PM. Yes, book that in.",
    )

    assert action is None


def test_calendar_action_detects_exact_conflict_check():
    action = _calendar_action_from_text(
        latest_text="Do I have another event at that moment?",
        recent_text="Friday at 2PM. Do I have another event at that moment?",
    )

    assert action
    assert action["tool_name"] == "check_calendar_conflict"
    assert "T14:00:00" in action["arguments"]["start_iso"]


def test_calendar_action_treats_exact_availability_question_as_conflict_check():
    action = _calendar_action_from_text(
        latest_text="Friday at 2PM to visit one of your properties. Is that time available?",
        recent_text="Friday at 2PM to visit one of your properties. Is that time available?",
    )

    assert action
    assert action["tool_name"] == "check_calendar_conflict"
    assert "T14:00:00" in action["arguments"]["start_iso"]


def test_calendar_action_detects_business_busy_question():
    action = _calendar_action_from_text(
        latest_text="Are you guys busy Friday at 2PM?",
        recent_text="Are you guys busy Friday at 2PM?",
    )

    assert action
    assert action["tool_name"] == "check_calendar_conflict"
    assert "T14:00:00" in action["arguments"]["start_iso"]


def test_calendar_action_checks_exact_viewing_request_before_llm():
    action = _calendar_action_from_text(
        latest_text="on Friday at 2PM?",
        recent_text="Can I come by and view it on Friday at 2PM?",
    )

    assert action
    assert action["tool_name"] == "check_calendar_conflict"
    assert "T14:00:00" in action["arguments"]["start_iso"]


def test_calendar_action_treats_booking_status_as_status_not_new_booking():
    action = _calendar_action_from_text(
        latest_text="Wait, did you book it?",
        recent_text="Friday at 2PM. Wait, did you book it?",
    )

    assert action is None


def test_calendar_action_prioritizes_explicit_booking_over_stale_availability_context():
    action = _calendar_action_from_text(
        latest_text="Can you book a viewing tomorrow at 7:30 PM?",
        recent_text="Are you free tomorrow at 7:30 PM? Can you book a viewing tomorrow at 7:30 PM?",
    )

    assert action
    assert action["tool_name"] == "prepare_and_confirm_calendar_booking"
    assert "T19:30:00" in action["arguments"]["start_iso"]


def test_calendar_action_handles_stuttered_viewing_time_request():
    action = _calendar_action_from_text(
        latest_text="Three bedroom villa, please. Could could we do it tomorrow around 7:30 PM?",
        recent_text="Three bedroom villa, please. Could could we do it tomorrow around 7:30 PM?",
    )

    assert action
    assert action["tool_name"] == "check_calendar_conflict"
    assert "T19:30:00" in action["arguments"]["start_iso"]


def test_calendar_action_treats_calendar_status_questions_as_status():
    assert _calendar_action_from_text(
        latest_text="What about the booking? The booking does not seem like it was booked.",
        recent_text="Are you free tomorrow at 7:30 PM?",
    ) is None
    assert _calendar_action_from_text(
        latest_text="Is it on the Google Calendar?",
        recent_text="Are you free tomorrow at 7:30 PM?",
    ) is None


def test_booking_status_and_suggested_slot_acceptance_cover_natural_confirmations():
    action = _suggested_booking_action(
        {
            "suggested_slots": [
                {"start_iso": "2026-05-30T09:00:00+02:00", "end_iso": "2026-05-30T09:30:00+02:00"}
            ]
        }
    )

    assert _accepts_suggested_slot("That's amazing.", recent_tail="Yes, tomorrow is open.")
    assert _accepts_suggested_slot("Perfect.", recent_tail="I can do this slot.")
    assert _booking_status_response(
        "What about the booking? It does not seem like it was booked.",
        last_booking_response=None,
        last_suggested_action=action,
    ).startswith("Not yet.")


def test_sms_status_questions_are_tool_turns_not_llm_promises():
    assert _asks_sms_status("Did you send it to me?")
    assert _asks_sms_status("I still haven't received any confirmation message.")


def test_calendar_response_suggests_next_slot_on_conflict():
    response = _calendar_response_text(
        {"tool_name": "check_calendar_conflict", "arguments": {}},
        {
            "ok": True,
            "outcome": "calendar_conflict_checked",
            "has_conflict": True,
            "suggested_slots": [{"start_iso": "2026-05-23T15:00:00+02:00"}],
        },
    )

    assert "already booked" in response
    assert "Saturday May 23 at 3 PM" in response


def test_calendar_response_for_open_exact_slot_keeps_slot_actionable():
    result = {
        "ok": True,
        "outcome": "calendar_conflict_checked",
        "has_conflict": False,
        "checked_slot": {
            "start_iso": "2026-05-29T14:00:00+02:00",
            "end_iso": "2026-05-29T14:30:00+02:00",
            "timezone": "Europe/Paris",
        },
    }

    response = _calendar_response_text({"tool_name": "check_calendar_conflict", "arguments": {}}, result)
    action = _suggested_booking_action(result)

    assert "Friday May 29 at 2 PM is open" in response
    assert action
    assert action["arguments"]["start_iso"] == "2026-05-29T14:00:00+02:00"


def test_calendar_suggestion_becomes_actionable_booking_option():
    result = {
        "ok": True,
        "outcome": "calendar_conflict_checked",
        "has_conflict": True,
        "suggested_slots": [{"start_iso": "2026-05-30T09:00:00+02:00", "end_iso": "2026-05-30T09:30:00+02:00"}],
    }

    action = _suggested_booking_action(result)

    assert action
    assert action["tool_name"] == "prepare_and_confirm_calendar_booking"
    assert action["arguments"]["start_iso"] == "2026-05-30T09:00:00+02:00"
    assert _accepts_suggested_slot("works.", recent_tail="Okay. That")


def test_availability_slot_becomes_actionable_booking_option():
    result = {
        "ok": True,
        "outcome": "available_slots",
        "slots": [{"start_iso": "2026-05-29T09:00:00+02:00", "end_iso": "2026-05-29T09:30:00+02:00"}],
    }

    action = _suggested_booking_action(result)

    assert action
    assert action["tool_name"] == "prepare_and_confirm_calendar_booking"
    assert action["arguments"]["start_iso"] == "2026-05-29T09:00:00+02:00"


def test_booking_status_uses_pending_suggestion_without_rebooking_old_slot():
    action = _suggested_booking_action(
        {
            "suggested_slots": [
                {"start_iso": "2026-05-30T09:00:00+02:00", "end_iso": "2026-05-30T09:30:00+02:00"}
            ]
        }
    )

    response = _booking_status_response(
        "Did you book it?",
        last_booking_response=None,
        last_suggested_action=action,
    )

    assert response
    assert response.startswith("Not yet.")
    assert "Saturday May 30 at 9 AM" in response


def test_calendar_action_detects_delete_request():
    action = _calendar_action_from_text(
        latest_text="Alright, now delete it.",
        recent_text="Done, I booked it for Monday at 2PM. Alright, now delete it.",
    )

    assert action
    assert action["tool_name"] == "cancel_calendar_booking"
