from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Any

from verbatim.config import Settings
from verbatim.integrations.store import CALENDAR_TOOL_NAMES


CLIENT_CONFIG_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class ClientConfig:
    profile: dict[str, Any]
    prompt: str
    knowledge_base: str
    integrations: dict[str, Any]

    @property
    def profile_id(self) -> str:
        return str(self.profile.get("profile_id") or "demo").strip() or "demo"


def client_config_dir() -> Path:
    return Path(os.environ.get("VERBATIM_CLIENT_CONFIG_DIR") or "./client")


def default_profile(settings: Settings) -> dict[str, Any]:
    return {
        "version": CLIENT_CONFIG_VERSION,
        "profile_id": settings.integrations.default_client_id or "demo",
        "business_name": "Demo Business",
        "assistant_name": "Alicia",
        "industry": "Real estate",
        "timezone": "Europe/Paris",
        "greeting": settings.prompt.greeting or "Hi, how can I help?",
        "transport_provider": settings.providers.transport_provider,
        "stt_provider": settings.providers.stt_provider,
        "deepgram_model": settings.providers.deepgram_model,
        "llm_provider": settings.providers.llm_provider,
        "llm_model": settings.providers.llm_model,
        "updated_at": utc_now_iso(),
    }


def default_integrations() -> dict[str, Any]:
    return {
        "version": CLIENT_CONFIG_VERSION,
        "updated_at": utc_now_iso(),
        "integrations": {
            "google_calendar": {"enabled": True, "disconnected_at": None},
            "twilio_sms": {"enabled": True, "disconnected_at": None},
            "knowledge_base": {"enabled": True, "disconnected_at": None},
            "call_notes": {"enabled": True, "disconnected_at": None},
            "calendly": {"enabled": False, "disconnected_at": None},
            "salesforce": {"enabled": False, "disconnected_at": None},
            "hubspot": {"enabled": False, "disconnected_at": None},
            "pipedrive": {"enabled": False, "disconnected_at": None},
            "slack": {"enabled": False, "disconnected_at": None},
            "gmail": {"enabled": False, "disconnected_at": None},
            "outlook_calendar": {"enabled": False, "disconnected_at": None},
            "google_sheets": {"enabled": False, "disconnected_at": None},
            "airtable": {"enabled": False, "disconnected_at": None},
            "notion": {"enabled": False, "disconnected_at": None},
            "stripe": {"enabled": False, "disconnected_at": None},
            "make": {"enabled": False, "disconnected_at": None},
            "zapier": {"enabled": False, "disconnected_at": None},
            "n8n": {"enabled": False, "disconnected_at": None},
            "webhook": {"enabled": False, "disconnected_at": None},
            "zenchef": {"enabled": False, "disconnected_at": None},
            "thefork": {"enabled": False, "disconnected_at": None},
            "whatsapp_business": {"enabled": False, "disconnected_at": None},
        },
    }


def integration_definitions(settings: Settings) -> list[dict[str, Any]]:
    return [
        {
            "id": "google_calendar",
            "label": "Google Calendar",
            "provider": "nango",
            "integration_key": settings.integrations.nango_google_calendar_integration_id,
            "description": "Check availability and book property viewings.",
            "implemented": True,
            "logo_path": "/static/assets/integrations/googlecalendar.svg",
            "required_env": ["NANGO_SECRET_KEY"],
            "allowed_tools": CALENDAR_TOOL_NAMES,
            "category": "Scheduling",
        },
        {
            "id": "twilio_sms",
            "label": "Twilio SMS",
            "provider": "direct",
            "integration_key": "twilio-messaging",
            "description": "Send SMS confirmations to the caller number.",
            "implemented": True,
            "logo_path": "/static/assets/integrations/twilio.svg",
            "required_env": ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER or TWILIO_MESSAGING_SERVICE_SID"],
            "allowed_tools": ["send_sms_followup"],
            "category": "Follow-up",
        },
        {
            "id": "knowledge_base",
            "label": "Knowledge Base",
            "provider": "local",
            "integration_key": "local-kb",
            "description": "Persistent local call context for this cloned agent.",
            "implemented": True,
            "logo_path": "/static/assets/integrations/knowledge-base.svg",
            "required_env": [],
            "allowed_tools": [],
            "category": "Local",
        },
        {
            "id": "call_notes",
            "label": "Call Notes",
            "provider": "local",
            "integration_key": "local-call-notes",
            "description": "Transcript and brief post-call summary.",
            "implemented": True,
            "logo_path": "/static/assets/integrations/call-notes.svg",
            "required_env": [],
            "allowed_tools": [],
            "category": "Local",
        },
        _nango(
            "calendly",
            "Calendly",
            settings.integrations.nango_calendly_integration_id,
            "Connect Calendly for scheduling and appointment workflows.",
            "calendly.svg",
            "Scheduling",
        ),
        _nango(
            "salesforce",
            "Salesforce",
            settings.integrations.nango_salesforce_integration_id,
            "Connect Salesforce for lead and CRM workflows.",
            "salesforce.svg",
            "CRM",
        ),
        _nango(
            "hubspot",
            "HubSpot",
            settings.integrations.nango_hubspot_integration_id,
            "Connect HubSpot for lead and CRM workflows.",
            "hubspot.svg",
            "CRM",
        ),
        _nango(
            "pipedrive",
            "Pipedrive",
            settings.integrations.nango_pipedrive_integration_id,
            "Connect Pipedrive for sales pipeline workflows.",
            "pipedrive.svg",
            "CRM",
        ),
        _nango(
            "slack",
            "Slack",
            settings.integrations.nango_slack_integration_id,
            "Connect Slack for internal handoff and alerts.",
            "slack.svg",
            "Human handoff",
        ),
        _nango(
            "gmail",
            "Gmail",
            settings.integrations.nango_gmail_integration_id,
            "Connect Gmail for future inbox and email follow-up workflows.",
            "gmail.svg",
            "Inbox",
        ),
        _nango(
            "outlook_calendar",
            "Outlook Calendar",
            settings.integrations.nango_outlook_calendar_integration_id,
            "Connect Outlook Calendar for scheduling workflows.",
            "microsoftoutlook.svg",
            "Scheduling",
        ),
        _nango(
            "google_sheets",
            "Google Sheets",
            settings.integrations.nango_google_sheets_integration_id,
            "Connect Google Sheets for lightweight lead tables and logs.",
            "googlesheets.svg",
            "Database",
        ),
        _nango(
            "airtable",
            "Airtable",
            settings.integrations.nango_airtable_integration_id,
            "Connect Airtable for lightweight CRM and inventory workflows.",
            "airtable.svg",
            "Database",
        ),
        _nango(
            "notion",
            "Notion",
            settings.integrations.nango_notion_integration_id,
            "Connect Notion for notes, pages, and knowledge workflows.",
            "notion.svg",
            "Knowledge",
        ),
        _nango(
            "stripe",
            "Stripe",
            settings.integrations.nango_stripe_integration_id,
            "Connect Stripe for future payment and billing workflows.",
            "stripe.svg",
            "Payments",
        ),
        _webhook(
            "make",
            "Make",
            "MAKE_WEBHOOK_URL",
            bool(settings.integrations.make_webhook_url),
            "Trigger a Make scenario through an inbound webhook.",
            "make.svg",
        ),
        _webhook(
            "zapier",
            "Zapier",
            "ZAPIER_WEBHOOK_URL",
            bool(settings.integrations.zapier_webhook_url),
            "Trigger a Zapier Zap through a webhook.",
            "zapier.svg",
        ),
        _webhook(
            "n8n",
            "n8n",
            "N8N_WEBHOOK_URL",
            bool(settings.integrations.n8n_webhook_url),
            "Trigger an n8n workflow through a webhook.",
            "n8n.svg",
        ),
        _webhook(
            "webhook",
            "Webhook",
            "VERBATIM_WEBHOOK_URL",
            bool(settings.integrations.generic_webhook_url),
            "Send events to a generic client-owned webhook endpoint.",
            "webhook.svg",
        ),
        _manual_api(
            "zenchef",
            "Zenchef",
            ["ZENCHEF_API_KEY"],
            bool(settings.integrations.zenchef_api_key),
            "Connect Zenchef credentials for future restaurant booking workflows.",
            "zenchef.svg",
            "Restaurant",
        ),
        _manual_api(
            "thefork",
            "TheFork",
            ["THEFORK_API_KEY"],
            bool(settings.integrations.thefork_api_key),
            "Connect TheFork credentials for future restaurant booking workflows.",
            "thefork.svg",
            "Restaurant",
        ),
        _manual_api(
            "whatsapp_business",
            "WhatsApp Business",
            ["WHATSAPP_BUSINESS_ACCESS_TOKEN", "WHATSAPP_BUSINESS_PHONE_NUMBER_ID"],
            bool(
                settings.integrations.whatsapp_business_access_token
                and settings.integrations.whatsapp_business_phone_number_id
            ),
            "Connect WhatsApp Business credentials for future message follow-up workflows.",
            "whatsapp.svg",
            "Messaging",
        ),
    ]


def _nango(
    integration_id: str,
    label: str,
    integration_key: str,
    description: str,
    logo_file: str,
    category: str,
) -> dict[str, Any]:
    return {
        "id": integration_id,
        "label": label,
        "provider": "nango",
        "integration_key": integration_key,
        "description": description,
        "implemented": True,
        "logo_path": f"/static/assets/integrations/{logo_file}",
        "required_env": ["NANGO_SECRET_KEY"],
        "allowed_tools": [],
        "category": category,
    }


def _webhook(
    integration_id: str,
    label: str,
    env_key: str,
    configured: bool,
    description: str,
    logo_file: str,
) -> dict[str, Any]:
    return {
        "id": integration_id,
        "label": label,
        "provider": "webhook",
        "integration_key": integration_id,
        "description": description,
        "implemented": True,
        "logo_path": f"/static/assets/integrations/{logo_file}",
        "required_env": [env_key],
        "configured": configured,
        "allowed_tools": [],
        "category": "Automation",
    }


def _manual_api(
    integration_id: str,
    label: str,
    required_env: list[str],
    configured: bool,
    description: str,
    logo_file: str,
    category: str,
) -> dict[str, Any]:
    return {
        "id": integration_id,
        "label": label,
        "provider": "manual_api",
        "integration_key": integration_id,
        "description": description,
        "implemented": True,
        "logo_path": f"/static/assets/integrations/{logo_file}",
        "required_env": required_env,
        "configured": configured,
        "allowed_tools": [],
        "category": category,
    }


def _placeholder(integration_id: str, label: str, logo_file: str, category: str) -> dict[str, Any]:
    return {
        "id": integration_id,
        "label": label,
        "provider": "placeholder",
        "integration_key": integration_id.replace("_", "-"),
        "description": "Integration slot reserved for a future adapter.",
        "implemented": False,
        "logo_path": f"/static/assets/integrations/{logo_file}",
        "required_env": [],
        "allowed_tools": [],
        "category": category,
    }


class ClientConfigStore:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else client_config_dir()
        self.profile_path = self.root / "profile.json"
        self.prompt_path = self.root / "prompt.md"
        self.kb_path = self.root / "kb.md"
        self.integrations_path = self.root / "integrations.json"

    def read(self, settings: Settings) -> ClientConfig:
        self.ensure_defaults(settings)
        return ClientConfig(
            profile=self._read_json(self.profile_path, default_profile(settings)),
            prompt=self.prompt_path.read_text(encoding="utf-8"),
            knowledge_base=self.kb_path.read_text(encoding="utf-8"),
            integrations=self._normalize_integrations(self._read_json(self.integrations_path, default_integrations())),
        )

    def ensure_defaults(self, settings: Settings) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.profile_path.exists():
            self._write_json(self.profile_path, default_profile(settings))
        if not self.prompt_path.exists():
            self.prompt_path.write_text((settings.prompt.system_prompt or "").strip() + "\n", encoding="utf-8")
        if not self.kb_path.exists():
            self.kb_path.write_text("", encoding="utf-8")
        if not self.integrations_path.exists():
            self._write_json(self.integrations_path, default_integrations())

    def update_profile(self, settings: Settings, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.read(settings).profile
        profile_id = str(current.get("profile_id") or settings.integrations.default_client_id or "demo")
        allowed = {
            "business_name",
            "assistant_name",
            "industry",
            "timezone",
            "greeting",
            "transport_provider",
            "stt_provider",
            "deepgram_model",
            "llm_provider",
            "llm_model",
        }
        updated = {**current, "profile_id": profile_id, "version": CLIENT_CONFIG_VERSION, "updated_at": utc_now_iso()}
        for key in allowed:
            if key in payload:
                value = payload.get(key)
                updated[key] = str(value).strip() if value is not None else ""
        self._write_json(self.profile_path, updated)
        return updated

    def update_prompt(self, settings: Settings, content: str) -> str:
        self.ensure_defaults(settings)
        cleaned = str(content or "").strip()
        if not cleaned:
            cleaned = settings.prompt.system_prompt.strip()
        self.prompt_path.write_text(cleaned + "\n", encoding="utf-8")
        return cleaned

    def update_kb(self, settings: Settings, content: str) -> str:
        self.ensure_defaults(settings)
        cleaned = str(content or "").strip()
        self.kb_path.write_text(cleaned + ("\n" if cleaned else ""), encoding="utf-8")
        return cleaned

    def reset_profile_prompt_kb(self, settings: Settings) -> ClientConfig:
        current = self.read(settings)
        profile = default_profile(settings)
        profile["profile_id"] = current.profile_id
        profile["updated_at"] = utc_now_iso()
        self._write_json(self.profile_path, profile)
        self.prompt_path.write_text((settings.prompt.system_prompt or "").strip() + "\n", encoding="utf-8")
        self.kb_path.write_text("", encoding="utf-8")
        return self.read(settings)

    def update_integrations(self, settings: Settings, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.read(settings).integrations
        integrations = deepcopy(current.get("integrations") or {})
        requested = payload.get("integrations") if isinstance(payload.get("integrations"), dict) else payload
        for integration_id, value in requested.items():
            if integration_id not in integrations:
                continue
            if isinstance(value, dict) and "enabled" in value:
                integrations[integration_id]["enabled"] = bool(value["enabled"])
                if value["enabled"]:
                    integrations[integration_id]["disconnected_at"] = None
            elif isinstance(value, bool):
                integrations[integration_id]["enabled"] = value
                if value:
                    integrations[integration_id]["disconnected_at"] = None
        updated = {"version": CLIENT_CONFIG_VERSION, "updated_at": utc_now_iso(), "integrations": integrations}
        self._write_json(self.integrations_path, updated)
        return updated

    def disconnect_integration(self, settings: Settings, integration_id: str) -> dict[str, Any]:
        current = self.read(settings).integrations
        integrations = deepcopy(current.get("integrations") or {})
        if integration_id not in integrations:
            raise KeyError(integration_id)
        integrations[integration_id]["enabled"] = False
        integrations[integration_id]["disconnected_at"] = utc_now_iso()
        updated = {"version": CLIENT_CONFIG_VERSION, "updated_at": utc_now_iso(), "integrations": integrations}
        self._write_json(self.integrations_path, updated)
        return updated

    def _normalize_integrations(self, value: dict[str, Any]) -> dict[str, Any]:
        defaults = default_integrations()
        normalized = deepcopy(defaults)
        raw_integrations = value.get("integrations") if isinstance(value.get("integrations"), dict) else {}
        for integration_id, state in raw_integrations.items():
            if integration_id not in normalized["integrations"] or not isinstance(state, dict):
                continue
            normalized["integrations"][integration_id].update(
                {
                    "enabled": bool(state.get("enabled")),
                    "disconnected_at": state.get("disconnected_at"),
                }
            )
        normalized["updated_at"] = value.get("updated_at") or normalized["updated_at"]
        return normalized

    def _read_json(self, path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return deepcopy(fallback)
        return payload if isinstance(payload, dict) else deepcopy(fallback)

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
