"""HTTP views for the payments app."""

from __future__ import annotations

import logging

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from payments.adapters.concrete import StripeAdapter
from payments.services import handle_payment_webhook, handle_stripe_webhook_event

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def payment_webhook_view(request: HttpRequest, gateway_key: str) -> HttpResponse:
    """CSRF-exempt webhook receiver — signature verified per adapter."""
    signature = request.headers.get("X-Payment-Signature", "")
    payment_tx = handle_payment_webhook(
        gateway_key=gateway_key,
        payload=request.body,
        signature=signature,
    )
    if payment_tx is None:
        return JsonResponse({"status": "ignored"}, status=404)
    return JsonResponse({"status": payment_tx.status})


@csrf_exempt
@require_POST
def stripe_webhook_view(request: HttpRequest) -> HttpResponse:
    """
    Real, signature-verified Stripe webhook — server-to-server confirmation
    path independent of the browser return-view redirect.

    Authenticated purely by the ``Stripe-Signature`` header (never by
    session/CSRF — this is a server-to-server call), verified via the
    official Stripe SDK over the raw request body.
    """
    signature = request.headers.get("Stripe-Signature", "")
    try:
        event_data = StripeAdapter().verify_webhook(payload=request.body, signature=signature)
    except ValueError:
        logger.warning("Rejected Stripe webhook: invalid or missing signature.")
        return JsonResponse({"status": "invalid_signature"}, status=400)

    if not isinstance(event_data, dict):
        logger.warning("Rejected Stripe webhook: malformed event body.")
        return JsonResponse({"status": "malformed_payload"}, status=400)

    event_id = event_data.get("id", "")
    if not event_id:
        logger.warning("Rejected Stripe webhook: missing event id.")
        return JsonResponse({"status": "missing_event_id"}, status=400)

    event_type = event_data.get("type", "")
    event, created = handle_stripe_webhook_event(
        event_id=event_id,
        event_type=event_type,
        event_data=event_data,
    )
    return JsonResponse({"status": event.status, "duplicate": not created}, status=200)
