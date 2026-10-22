"""
Runtime configuration for the WhatsApp integration (Gupshup WhatsApp Business API).

"""

from __future__ import annotations

from django.conf import settings

API_BASE_URL = "https://api.gupshup.io"


def is_enabled() -> bool:
    """Master switch. When False, order events never queue a WhatsApp message."""
    return bool(getattr(settings, "WHATSAPP_ENABLED", False))


def api_key() -> str:
    return (getattr(settings, "GUPSHUP_API_KEY", "") or "").strip()


def source_number() -> str:
    return (getattr(settings, "GUPSHUP_SOURCE_NUMBER", "") or "").strip()


def app_name() -> str:
    return (getattr(settings, "GUPSHUP_APP_NAME", "") or "").strip()


def webhook_secret() -> str:
    return (getattr(settings, "GUPSHUP_WEBHOOK_SECRET", "") or "").strip()


def otp_template_id() -> str:
    from core.services import get_site_settings

    return (get_site_settings().whatsapp_otp_template_id or "").strip()


def default_country_code() -> str:
    return (getattr(settings, "WHATSAPP_DEFAULT_COUNTRY_CODE", "") or "91").strip().lstrip("+")


def request_timeout() -> int:
    return int(getattr(settings, "WHATSAPP_REQUEST_TIMEOUT", 10) or 10)


def is_configured() -> bool:
    """True when the credentials needed to *send* are present."""
    return bool(api_key() and source_number() and app_name())
