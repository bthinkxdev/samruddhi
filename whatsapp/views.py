"""
Meta WhatsApp webhook endpoint.

"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from whatsapp import conf
from whatsapp.services import process_webhook_payload

logger = logging.getLogger(__name__)


def verify_signature(raw_body: bytes, signature_header: str) -> bool:
    """Constant-time check of Meta's ``sha256=<hex>`` signature."""
    secret = conf.app_secret()
    if not secret:
        # Without an App Secret we cannot authenticate Meta. Allow only in local DEBUG.
        return bool(settings.DEBUG)
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.split("=", 1)[1])


@csrf_exempt
@require_http_methods(["GET", "POST"])
def webhook(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        token = conf.webhook_verify_token()
        if (
            token
            and request.GET.get("hub.mode") == "subscribe"
            and hmac.compare_digest(request.GET.get("hub.verify_token", ""), token)
        ):
            return HttpResponse(request.GET.get("hub.challenge", ""), content_type="text/plain")
        return HttpResponseForbidden("Verification failed.")

    if not verify_signature(request.body, request.headers.get("X-Hub-Signature-256", "")):
        logger.warning(
            "WhatsApp webhook: invalid signature from %s", request.META.get("REMOTE_ADDR")
        )
        return HttpResponseForbidden("Invalid signature.")

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"error": "invalid json"}, status=400)

    try:
        counts = process_webhook_payload(payload)
    except Exception:  # noqa: BLE001 — always 200 so Meta doesn't hammer retries; we log it
        logger.exception("WhatsApp webhook processing failed")
        counts = {}
    return JsonResponse({"ok": True, **counts})
