"""
Runtime configuration for the WhatsApp integration.

"""

from __future__ import annotations

from django.conf import settings

GRAPH_API_BASE_URL = "https://graph.facebook.com"


def is_enabled() -> bool:
    """Master switch. When False, order events never queue a WhatsApp message."""
    return bool(getattr(settings, "WHATSAPP_ENABLED", False))


def access_token() -> str:
    return (getattr(settings, "WHATSAPP_ACCESS_TOKEN", "") or "").strip()


def phone_number_id() -> str:
    return (getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "") or "").strip()


def api_version() -> str:
    return (getattr(settings, "WHATSAPP_API_VERSION", "") or "v21.0").strip()


def app_secret() -> str:
    return (getattr(settings, "WHATSAPP_APP_SECRET", "") or "").strip()


def webhook_verify_token() -> str:
    return (getattr(settings, "WHATSAPP_WEBHOOK_VERIFY_TOKEN", "") or "").strip()


def default_country_code() -> str:
    return (getattr(settings, "WHATSAPP_DEFAULT_COUNTRY_CODE", "") or "91").strip().lstrip("+")


def request_timeout() -> int:
    return int(getattr(settings, "WHATSAPP_REQUEST_TIMEOUT", 10) or 10)


def is_configured() -> bool:
    """True when the credentials needed to *send* are present."""
    return bool(access_token() and phone_number_id())
