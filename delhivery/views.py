import json
import logging
import re

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from orders.models import Order, OrderStatus
from orders.services import ORDER_STATUS_RANK, transition_order_status

logger = logging.getLogger(__name__)

#Delhivery status-string -> our OrderStatus. Anything else is logged and ignored.
#
#"Manifested"/"Pickup Scheduled" map to READY_TO_SHIP (not AWB creation — the AWB
#already exists from CONFIRMED; these events only confirm Delhivery accepted the
#shipment). READY_TO_SHIP can also be set manually by the warehouse via the
#dashboard — whichever happens first; the regression guard below just no-ops the
#other one. PICKED_UP / IN_TRANSIT / OUT_FOR_DELIVERY / DELIVERED are reachable only
#through this webhook — admins cannot set them manually (see
#orders.services.ALLOWED_STATUS_TRANSITIONS).
DELHIVERY_TO_ORDER_STATUS = {
    "manifested": OrderStatus.READY_TO_SHIP,
    "pickup scheduled": OrderStatus.READY_TO_SHIP,
    "picked up": OrderStatus.PICKED_UP,
    "in transit": OrderStatus.IN_TRANSIT,
    "dispatched": OrderStatus.IN_TRANSIT,
    "out for delivery": OrderStatus.OUT_FOR_DELIVERY,
    "delivered": OrderStatus.DELIVERED,
    "rto in transit": OrderStatus.CANCELLED,
    "rto delivered": OrderStatus.CANCELLED,
    "rto": OrderStatus.CANCELLED,
    "cancelled": OrderStatus.CANCELLED,
}


def _extract_event(payload: dict) -> dict:
    """
    Normalize a Delhivery webhook payload into {waybill, status, status_datetime, order_number}.

    Accepts Delhivery's commonly-documented nested shape (Shipment.AWB /
    Shipment.Status.Status / Shipment.Status.StatusDateTime / Shipment.ReferenceNo) as
    well as a flat fallback shape (waybill/awb, status, order_id/ref_num). The exact
    production payload hasn't been verified against a live Delhivery sample, so both
    are supported defensively rather than assuming one schema.
    """
    shipment_block = payload.get("Shipment") if isinstance(payload.get("Shipment"), dict) else {}
    status_block = shipment_block.get("Status") if isinstance(shipment_block.get("Status"), dict) else {}

    waybill = (
        shipment_block.get("AWB")
        or payload.get("waybill")
        or payload.get("awb")
        or payload.get("Waybill")
        or ""
    )
    status_str = status_block.get("Status") or payload.get("status") or ""
    status_datetime = status_block.get("StatusDateTime") or payload.get("status_datetime") or ""
    order_number = (
        shipment_block.get("ReferenceNo")
        or payload.get("ref_num")
        or payload.get("order_id")
        or ""
    )
    return {
        "waybill": str(waybill).strip(),
        "status": str(status_str).strip().lower(),
        "status_datetime": str(status_datetime).strip(),
        "order_number": str(order_number).strip(),
    }


@csrf_exempt
@require_POST
def delhivery_webhook(request):
    """
    Endpoint for receiving Delhivery scan push webhooks.

    Delhivery is the source of truth for shipment progress: every accepted event is
    deduped and rank-guarded against backward regression before being applied.
    """
    #1. fail-closed auth — an unconfigured token must reject, never silently skip
    expected_token = getattr(settings, "DELHIVERY_WEBHOOK_TOKEN", "")
    if not expected_token:
        logger.error("DELHIVERY_WEBHOOK_TOKEN is not configured; rejecting webhook.")
        return JsonResponse({"error": "Webhook not configured"}, status=503)

    provided_token = request.headers.get("X-Delhivery-Token")
    if provided_token != expected_token:
        logger.warning("Delhivery webhook authentication failed.")
        return JsonResponse({"error": "Unauthorized"}, status=401)

    #2. parse payload
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        logger.error("Invalid JSON payload received in Delhivery webhook.")
        return JsonResponse({"error": "Invalid payload"}, status=400)

    logger.info(f"Received Delhivery webhook payload: {payload}")

    event = _extract_event(payload)
    if not event["waybill"] and not event["order_number"]:
        return JsonResponse({"error": "Missing waybill/order reference"}, status=400)

    #2b. Delhivery's Scan Push validation test sends their fixed sample payload with the
    #literal placeholder AWB "XXXXXXXXXXXX" (all X characters) — it never corresponds to a
    #real shipment for any merchant. Real AWBs are always numeric, so this check can never
    #collide with genuine traffic. Acknowledge with 200 OK without touching shipment lookup.
    if event["waybill"] and re.fullmatch(r"[Xx]+", event["waybill"]):
        logger.info("Delhivery webhook validation test payload received (placeholder AWB); acknowledging.")
        return JsonResponse({"status": "test_payload_acknowledged"})

    #3. resolve the shipment — waybill first (always present on a real scan push)
    from delhivery.models import DelhiveryShipment

    shipment = None
    if event["waybill"]:
        shipment = (
            DelhiveryShipment.objects.select_related("order")
            .filter(waybill_number=event["waybill"])
            .first()
        )
    if shipment is None and event["order_number"]:
        order = Order.objects.filter(order_number=event["order_number"]).first()
        if order is not None:
            shipment = DelhiveryShipment.objects.select_related("order").filter(order=order).first()

    if shipment is None:
        logger.warning(f"No Delhivery shipment found for webhook event: {event}")
        return JsonResponse({"error": "Shipment not found"}, status=404)

    order = shipment.order

    #4. dedup — ignore an event identical to the last one we applied
    signature = f"{event['waybill']}|{event['status']}|{event['status_datetime'] or event['status']}"
    if signature and signature == shipment.last_event_signature:
        logger.info(f"Duplicate Delhivery webhook event ignored for {order.order_number}: {signature}")
        return JsonResponse({"status": "duplicate_ignored"})

    #5. always record the raw tracking status + signature, even if it has no OrderStatus mapping
    shipment.tracking_status = event["status"].title() or shipment.tracking_status
    shipment.last_status_at = timezone.now()
    shipment.last_event_signature = signature
    shipment.save(
        update_fields=["tracking_status", "last_status_at", "last_event_signature", "updated_at"]
    )

    target_status = DELHIVERY_TO_ORDER_STATUS.get(event["status"])
    if not target_status or target_status == order.order_status:
        return JsonResponse({"status": "success"})

    #6. regression guard — a stale/out-of-order scan must never move status backward.
    #CANCELLED/REFUNDED are absorbing and always allowed: an RTO/cancel can legitimately
    #arrive from any fulfillment rank.
    current_rank = ORDER_STATUS_RANK.get(order.order_status)
    target_rank = ORDER_STATUS_RANK.get(target_status)
    is_absorbing_target = target_status in (OrderStatus.CANCELLED, OrderStatus.REFUNDED)
    if (
        not is_absorbing_target
        and current_rank is not None
        and target_rank is not None
        and target_rank <= current_rank
    ):
        logger.warning(
            f"Ignoring backward/out-of-order Delhivery status for {order.order_number}: "
            f"{order.order_status} -> {target_status}"
        )
        return JsonResponse({"status": "ignored_regression"})

    try:
        transition_order_status(
            order=order,
            new_status=target_status,
            note=f"Delhivery update: {event['status'].title()}",
            force=True,  #Delhivery is the fulfillment source of truth
        )
        logger.info(f"Order {order.order_number} marked as {target_status} via webhook.")
    except Exception as e:
        logger.error(f"Failed to transition order {order.order_number} to {target_status}: {e}")
        return JsonResponse({"error": "Failed to update order"}, status=500)

    return JsonResponse({"status": "success"})
