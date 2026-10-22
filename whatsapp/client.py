"""
Thin HTTP client for the Gupshup WhatsApp Business API (``/wa/api/v1/...``).

"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional, Sequence

import requests

from whatsapp import conf
from whatsapp.exceptions import WhatsAppAPIError, WhatsAppNotConfigured, WhatsAppRetryableError

logger = logging.getLogger(__name__)


class GupshupClient:
    """Sends messages through one Gupshup WhatsApp source number."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        source: Optional[str] = None,
        app_name: Optional[str] = None,
        timeout: Optional[int] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else conf.api_key()
        self.source = source if source is not None else conf.source_number()
        self.app_name = app_name if app_name is not None else conf.app_name()
        self.timeout = timeout or conf.request_timeout()
        self.session = session or requests.Session()
        if not (self.api_key and self.source and self.app_name):
            raise WhatsAppNotConfigured(
                "GUPSHUP_API_KEY, GUPSHUP_SOURCE_NUMBER and GUPSHUP_APP_NAME must be set."
            )

    @property
    def template_url(self) -> str:
        return f"{conf.API_BASE_URL}/wa/api/v1/template/msg"

    @property
    def msg_url(self) -> str:
        return f"{conf.API_BASE_URL}/wa/api/v1/msg"

    # ------------------------------------------------------------------ #
    # Payload builders (also used to store request_payload in logs)
    # ------------------------------------------------------------------ #

    def build_template_payload(
        self,
        *,
        to: str,
        template_id: str,
        body_params: Sequence[str] = (),
        button_url_param: Optional[str] = None,
    ) -> dict[str, Any]:
        # Gupshup fills every template placeholder — body variables and a dynamic
        # URL-button suffix alike — from one ordered params list.
        params = [str(p) for p in body_params]
        if button_url_param:
            params = [*params, str(button_url_param)]
        return {
            "channel": "whatsapp",
            "source": self.source,
            "destination": to,
            "src.name": self.app_name,
            "template": json.dumps({"id": template_id, "params": params}),
        }

    def build_text_payload(self, *, to: str, text: str) -> dict[str, Any]:
        return {
            "channel": "whatsapp",
            "source": self.source,
            "destination": to,
            "src.name": self.app_name,
            "message": json.dumps({"type": "text", "text": text}),
        }

    # ------------------------------------------------------------------ #
    # Sender
    # ------------------------------------------------------------------ #

    def send_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST a prepared form payload. Returns Gupshup's JSON (contains ``messageId``)."""
        url = self.template_url if "template" in payload else self.msg_url
        headers = {
            "apikey": self.api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        try:
            response = self.session.post(url, data=payload, headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise WhatsAppRetryableError(f"Network error calling Gupshup API: {exc}") from exc

        try:
            data = response.json()
        except ValueError:
            data = {"raw": response.text[:1000]}

        if (
            response.status_code < 300
            and isinstance(data, dict)
            and data.get("status") == "submitted"
        ):
            return data

        message = (
            data.get("message") if isinstance(data, dict) else None
        ) or f"HTTP {response.status_code}"

        exc_class = (
            WhatsAppRetryableError
            if response.status_code == 429 or response.status_code >= 500
            else WhatsAppAPIError
        )
        logger.warning(
            "Gupshup API error status=%s message=%s",
            response.status_code,
            message,
        )
        raise exc_class(message, code=None, status_code=response.status_code, payload=data)

    def send_template(self, **kwargs: Any) -> dict[str, Any]:
        return self.send_payload(self.build_template_payload(**kwargs))

    def send_text(self, **kwargs: Any) -> dict[str, Any]:
        return self.send_payload(self.build_text_payload(**kwargs))


def extract_message_id(response_data: dict[str, Any]) -> str:
    """Gupshup's message id (used to correlate later webhook events)."""
    return response_data.get("messageId") or ""
