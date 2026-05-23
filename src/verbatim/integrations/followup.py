from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from verbatim.config import Settings


def twilio_sms_configured(settings: Settings) -> bool:
    return bool(
        settings.integrations.twilio_account_sid
        and settings.integrations.twilio_auth_token
        and (settings.integrations.twilio_from_number or settings.integrations.twilio_messaging_service_sid)
    )


def twilio_whatsapp_configured(settings: Settings) -> bool:
    return bool(
        settings.integrations.twilio_account_sid
        and settings.integrations.twilio_auth_token
        and settings.integrations.twilio_whatsapp_from
    )


def resend_configured(settings: Settings) -> bool:
    return bool(settings.integrations.resend_api_key and settings.integrations.resend_from_email)


def followup_tools_ready(settings: Settings) -> bool:
    return twilio_sms_configured(settings)


@dataclass(frozen=True)
class FollowupService:
    settings: Settings
    client_id: str

    async def send_sms_followup(self, *, to_phone: str | None, body: str, channel: str = "sms") -> dict[str, Any]:
        channel = (channel or "sms").strip().lower()
        if channel == "whatsapp":
            return await self._send_twilio_message(to_phone=to_phone, body=body, channel="whatsapp")
        return await self._send_twilio_message(to_phone=to_phone, body=body, channel="sms")

    async def send_email_followup(self, *, to_email: str | None, subject: str, body: str) -> dict[str, Any]:
        if not resend_configured(self.settings):
            return _safe_failure("missing_resend_config", "Email is not configured yet.")
        to_email = _clean(to_email)
        if not to_email:
            return _safe_failure("missing_email_destination", "What email should I use?")
        payload = {
            "from": self.settings.integrations.resend_from_email,
            "to": [to_email],
            "subject": subject[:160] or "Your property follow-up",
            "text": body[:4000] or self.settings.integrations.followup_email_default_body,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {self.settings.integrations.resend_api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            return _safe_failure("email_send_failed", f"Email failed safely: {exc.__class__.__name__}")
        return {
            "ok": True,
            "outcome": "email_sent",
            "integration_provider": "resend",
            "message_id": str(data.get("id") or ""),
            "destination_preview": _mask_email(to_email),
            "message": "Email sent.",
        }

    async def _send_twilio_message(self, *, to_phone: str | None, body: str, channel: str) -> dict[str, Any]:
        if channel == "whatsapp":
            configured = twilio_whatsapp_configured(self.settings)
            missing_outcome = "missing_twilio_whatsapp_config"
            missing_message = "WhatsApp is not configured yet."
        else:
            configured = twilio_sms_configured(self.settings)
            missing_outcome = "missing_twilio_sms_config"
            missing_message = "SMS is not configured yet."
        if not configured:
            return _safe_failure(missing_outcome, missing_message)
        to_phone = _clean(to_phone)
        if not to_phone:
            return _safe_failure("missing_phone_destination", "What phone number should I send it to?")
        account_sid = self.settings.integrations.twilio_account_sid or ""
        payload = {"To": _twilio_destination(to_phone, channel=channel), "Body": body[:1200] or self.settings.integrations.followup_sms_default_body}
        if channel == "whatsapp":
            payload["From"] = self.settings.integrations.twilio_whatsapp_from or ""
        elif self.settings.integrations.twilio_messaging_service_sid:
            payload["MessagingServiceSid"] = self.settings.integrations.twilio_messaging_service_sid
        else:
            payload["From"] = self.settings.integrations.twilio_from_number or ""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
                    data=payload,
                    auth=(account_sid, self.settings.integrations.twilio_auth_token or ""),
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            return _safe_failure("message_send_failed", f"Message failed safely: {exc.__class__.__name__}")
        return {
            "ok": True,
            "outcome": "whatsapp_sent" if channel == "whatsapp" else "sms_sent",
            "integration_provider": "twilio",
            "message_id": str(data.get("sid") or ""),
            "destination_preview": _mask_phone(to_phone),
            "message": "Message sent.",
        }


def _twilio_destination(value: str, *, channel: str) -> str:
    if channel == "whatsapp" and not value.lower().startswith("whatsapp:"):
        return f"whatsapp:{value}"
    return value


def _safe_failure(outcome: str, message: str) -> dict[str, Any]:
    return {"ok": False, "outcome": outcome, "message": message[:240]}


def _clean(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _mask_phone(value: str) -> str:
    digits = "".join(char for char in value if char.isdigit())
    if len(digits) <= 4:
        return "***"
    return f"***{digits[-4:]}"


def _mask_email(value: str) -> str:
    name, _, domain = value.partition("@")
    if not domain:
        return "***"
    return f"{name[:1]}***@{domain}"
