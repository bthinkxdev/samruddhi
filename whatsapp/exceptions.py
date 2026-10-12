"""Exceptions raised by the WhatsApp integration."""

from __future__ import annotations

from typing import Any, Optional


class WhatsAppError(Exception):
    """Base class for every WhatsApp integration error."""


class WhatsAppNotConfigured(WhatsAppError):
    """Access token / phone number id missing."""


class InvalidPhoneNumber(WhatsAppError):
    """Phone number cannot be normalised to E.164 digits."""


class WhatsAppAPIError(WhatsAppError):
    """Meta rejected the request — permanent, do not retry."""

    def __init__(
        self,
        message: str,
        *,
        code: Optional[int] = None,
        status_code: Optional[int] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.payload = payload or {}


class WhatsAppRetryableError(WhatsAppAPIError):
    """Network failure, 5xx or rate limiting — safe to retry later."""
