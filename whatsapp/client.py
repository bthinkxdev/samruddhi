"""
Thin HTTP client for the Meta WhatsApp Cloud API (Graph API ``/{phone-number-id}/messages``).

"""

from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

import requests

from whatsapp import conf
from whatsapp.exceptions import WhatsAppAPIError, WhatsAppNotConfigured, WhatsAppRetryableError

logger = logging.getLogger(__name__)

# meta error codes that are temporary (rate limits / transient platform errors).
# https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes
RETRYABLE_ERROR_CODES = {1, 2, 4, 80007, 130429, 131000, 131048, 131056}


class WhatsAppClient:
    """Sends messages through one WhatsApp Business phone number."""

    def __init__(
        self,
        *,
        access_token: Optional[str] = None,
        phone_number_id: Optional[str] = None,
        api_version: Optional[str] = None,
        timeout: Optional[int] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.access_token = access_token if access_token is not None else conf.access_token()
        self.phone_number_id = (
            phone_number_id if phone_number_id is not None else conf.phone_number_id()
        )
        self.api_version = api_version or conf.api_version()
        self.timeout = timeout or conf.request_timeout()
        self.session = session or requests.Session()
        if not (self.access_token and self.phone_number_id):
            raise WhatsAppNotConfigured(
                "WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID must be set."
            )

    @property
    def messages_url(self) -> str:
        return f"{conf.GRAPH_API_BASE_URL}/{self.api_version}/{self.phone_number_id}/messages"

    # ------------------------------------------------------------------ #
    # Payload builders (pure — also used to store request_payload in logs)
    # ------------------------------------------------------------------ #

    @staticmethod
    def build_template_payload(
        *,
        to: str,
        template_name: str,
        language_code: str = "en",
        body_params: Sequence[str] = (),
        button_url_param: Optional[str] = None,
    ) -> dict[str, Any]:
        components: list[dict[str, Any]] = []
        if body_params:
            components.append(
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": str(p)} for p in body_params],
                }
            )
        if button_url_param:
            components.append(
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": "0",
                    "parameters": [{"type": "text", "text": str(button_url_param)}],
                }
            )
        template: dict[str, Any] = {"name": template_name, "language": {"code": language_code}}
        if components:
            template["components"] = components
        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "template",
            "template": template,
        }

    @staticmethod
    def build_text_payload(*, to: str, text: str, preview_url: bool = False) -> dict[str, Any]:
        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"body": text, "preview_url": preview_url},
        }

    # ------------------------------------------------------------------ #
    # Senders
    # ------------------------------------------------------------------ #

    def send_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST a prepared payload. Returns Meta's JSON (contains ``messages[0].id``)."""
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        try:
            response = self.session.post(
                self.messages_url, json=payload, headers=headers, timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise WhatsAppRetryableError(f"Network error calling WhatsApp API: {exc}") from exc

        try:
            data = response.json()
        except ValueError:
            data = {"raw": response.text[:1000]}

        if response.status_code < 300:
            return data

        error = data.get("error", {}) if isinstance(data, dict) else {}
        code = error.get("code")
        details = (error.get("error_data") or {}).get("details") or ""
        message = error.get("message") or f"HTTP {response.status_code}"
        if details:
            message = f"{message} — {details}"

        exc_class = (
            WhatsAppRetryableError
            if response.status_code == 429
            or response.status_code >= 500
            or code in RETRYABLE_ERROR_CODES
            else WhatsAppAPIError
        )
        logger.warning(
            "WhatsApp API error status=%s code=%s message=%s",
            response.status_code,
            code,
            message,
        )
        raise exc_class(message, code=code, status_code=response.status_code, payload=data)

    def send_template(self, **kwargs: Any) -> dict[str, Any]:
        return self.send_payload(self.build_template_payload(**kwargs))

    def send_text(self, **kwargs: Any) -> dict[str, Any]:
        return self.send_payload(self.build_text_payload(**kwargs))


def extract_message_id(response_data: dict[str, Any]) -> str:
    """Meta's message id (``wamid.xxx``) from a successful send response."""
    messages = response_data.get("messages") or []
    return (messages[0].get("id") if messages else "") or ""
