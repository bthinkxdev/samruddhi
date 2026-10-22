"""
Gupshup WhatsApp webhook endpoint.

Gupshup does not sign its webhook calls (no HMAC, no verification handshake like
Meta's hub.challenge). Our own protection is a shared-secret ``token`` query
parameter on the callback URL registered in the Gupshup dashboard.
"""

from __future__ import annotations

import hmac
import json
import logging

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from whatsapp import conf
from whatsapp.services import process_webhook_payload

logger = logging.getLogger(__name__)


def _verify_token(request: HttpRequest) -> bool:
    secret = conf.webhook_secret()
    if not secret:
        # Without a shared secret we cannot authenticate Gupshup. Allow only in local DEBUG.
        return bool(settings.DEBUG)
    supplied = request.GET.get("token", "")
    return bool(supplied) and hmac.compare_digest(supplied, secret)


@csrf_exempt
@require_POST
def webhook(request: HttpRequest) -> HttpResponse:
    if not _verify_token(request):
        logger.warning(
            "Gupshup webhook: invalid/missing token from %s", request.META.get("REMOTE_ADDR")
        )
        return HttpResponseForbidden("Invalid token.")

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"error": "invalid json"}, status=400)

    try:
        counts = process_webhook_payload(payload)
    except Exception:  # noqa: BLE001 — always 200 so Gupshup doesn't hammer retries; we log it
        logger.exception("Gupshup webhook processing failed")
        counts = {}
    return JsonResponse({"ok": True, **counts})
