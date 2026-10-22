"""
Write operations and business rules for the WhatsApp app (Gupshup WhatsApp Business API).

"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from datetime import timezone as dt_timezone
from typing import Any, Iterable, Optional, Sequence

from django.db import transaction
from django.utils import timezone

from whatsapp import conf
from whatsapp.client import GupshupClient, extract_message_id
from whatsapp.exceptions import (
    InvalidPhoneNumber,
    WhatsAppAPIError,
    WhatsAppNotConfigured,
    WhatsAppRetryableError,
)
from whatsapp.models import (
    MessageDirection,
    MessageStatus,
    WhatsAppMessage,
    WhatsAppTemplate,
)

logger = logging.getLogger(__name__)

# delivery receipts can arrive out of order (e.g. "delivered" before "sent");
# status only ever moves forward along this rank. FAILED is handled separately.
STATUS_RANK = {
    MessageStatus.QUEUED: 0,
    MessageStatus.SENT: 1,
    MessageStatus.DELIVERED: 2,
    MessageStatus.READ: 3,
}

# receipt statuses Gupshup sends in "message-event" webhooks ("enqueued" has no
# corresponding MessageStatus and is ignored).
RECEIPT_STATUSES = {"sent", "delivered", "read", "failed"}

# inbound replies that opt the customer out of WhatsApp order updates.
OPT_OUT_KEYWORDS = {"STOP", "STOP ALL", "UNSUBSCRIBE", "CANCEL UPDATES"}

PARAM_MAX_LENGTH = 1000


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def normalize_phone(raw: str, *, country_code: Optional[str] = None) -> str:
    """
    Normalise a stored phone number to the digits-only international format Gupshup expects.

    """
    raw = (raw or "").strip()
    cc = (country_code or conf.default_country_code()).lstrip("+")
    digits = re.sub(r"\D", "", raw)

    if raw.startswith("+"):
        pass
    elif digits.startswith("00"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = cc + digits[1:]
    elif len(digits) == 10:
        digits = cc + digits

    if not 11 <= len(digits) <= 15:
        raise InvalidPhoneNumber(f"Cannot normalise phone number {raw!r}.")
    return digits


def _clean_param(value: Any) -> str:
    """
    WhatsApp rejects template parameters that are empty, contain newlines/tabs or more
    than four consecutive spaces — this applies regardless of BSP, including Gupshup.
    """
    text = re.sub(r"[\r\n\t]+", " ", str(value if value is not None else "")).strip()
    text = re.sub(r" {4,}", "   ", text)
    return text[:PARAM_MAX_LENGTH] or "-"


def build_order_context(order: Any) -> dict[str, str]:
    """Every value an admin can map to a template placeholder (see TEMPLATE_VARIABLES)."""
    from core.services import get_site_settings

    profile = getattr(order, "customer_profile", None)
    user = getattr(profile, "user", None)
    customer_name = (getattr(user, "first_name", "") or "").strip()
    if not customer_name:
        customer_name = (order.customer_display_name or "").split(" ")[0] or "Customer"

    currency = getattr(order, "currency", None)
    symbol = getattr(currency, "symbol", "") or getattr(currency, "code", "") or "₹"

    items = list(order.items.select_related("product").all()[:4])
    names = [item.product.name for item in items[:3]]
    order_items = ", ".join(names) + (" and more" if len(items) > 3 else "")

    tracking_number = ""
    if _has_shipment(order):
        tracking_number = order.delhivery_shipment.waybill_number or ""

    return {
        "customer_name": customer_name,
        "order_number": order.order_number or str(order.pk),
        "store_name": get_site_settings().site_name or "",
        "order_total": f"{symbol} {order.total_amount}",
        "order_status": order.get_order_status_display(),
        "order_items": order_items,
        "tracking_number": tracking_number,
    }


def _has_shipment(order: Any) -> bool:
    from django.core.exceptions import ObjectDoesNotExist

    try:
        return order.delhivery_shipment is not None
    except ObjectDoesNotExist:
        return False


def get_active_template(event: str) -> Optional[WhatsAppTemplate]:
    return WhatsAppTemplate.objects.filter(event=event, is_active=True).first()


def _enqueue(message_id: int) -> None:
    """Hand the message to Celery. Never raises (broker outages must not break callers)."""
    from whatsapp.tasks import send_message_task

    try:
        send_message_task.delay(message_id=message_id)
    except Exception:  # noqa: BLE001 — logged; the row stays QUEUED and can be retried
        logger.exception("Could not enqueue WhatsApp message %s", message_id)


# --------------------------------------------------------------------------- #
# Outbound
# --------------------------------------------------------------------------- #


def queue_order_event(
    *,
    order: Any,
    event: str,
    phone: Optional[str] = None,
) -> Optional[WhatsAppMessage]:
    """
    Queue the WhatsApp template mapped to ``event`` for this order.

    """
    if not conf.is_enabled():
        logger.debug("WhatsApp disabled — skipping %s for order %s", event, order.pk)
        return None

    template = get_active_template(event)
    if template is None:
        logger.info("No active WhatsApp template for event %s — skipping.", event)
        return None

    if phone is None:
        profile = getattr(order, "customer_profile", None)
        phone = getattr(profile, "phone", "") or ""
    try:
        to = normalize_phone(phone)
    except InvalidPhoneNumber:
        logger.warning("Order %s: invalid WhatsApp phone %r — skipping.", order.pk, phone)
        return None

    context = build_order_context(order)
    body_params = [_clean_param(context.get(key)) for key in template.body_variables]
    button_param = (
        _clean_param(context.get(template.button_url_variable))
        if template.button_url_variable
        else ""
    )

    message, created = WhatsAppMessage.objects.get_or_create(
        idempotency_key=f"order:{order.pk}:{event}",
        defaults={
            "direction": MessageDirection.OUTBOUND,
            "phone": to,
            "event": event,
            "message_type": "template",
            "template_id": template.template_id,
            "body_params": body_params,
            "button_url_param": button_param,
            "order": order,
            "status": MessageStatus.QUEUED,
        },
    )
    if not created:
        logger.info("WhatsApp %s for order %s already queued/sent — skipping.", event, order.pk)
        return message

    message_id = message.pk
    transaction.on_commit(lambda: _enqueue(message_id))
    return message


def _build_payload(message: WhatsAppMessage, client: GupshupClient) -> dict[str, Any]:
    if message.message_type == "text":
        return client.build_text_payload(to=message.phone, text=message.text)
    return client.build_template_payload(
        to=message.phone,
        template_id=message.template_id,
        body_params=message.body_params or [],
        button_url_param=message.button_url_param or None,
    )


def _mark_failed(
    message: WhatsAppMessage, exc: Exception, *, status: str = MessageStatus.FAILED
) -> None:
    message.status = status
    message.error_code = str(getattr(exc, "code", "") or "")[:20]
    message.error_message = str(exc)[:2000]
    message.response_payload = getattr(exc, "payload", {}) or {}
    if status == MessageStatus.FAILED:
        message.failed_at = timezone.now()
    message.save()


def deliver_message(
    message_id: int, *, client: Optional[GupshupClient] = None
) -> Optional[WhatsAppMessage]:
    """
    Send one QUEUED outbound message through Gupshup.

    """
    retry_exc: Optional[WhatsAppRetryableError] = None

    with transaction.atomic():
        message = WhatsAppMessage.objects.select_for_update().filter(pk=message_id).first()
        if (
            message is None
            or message.direction != MessageDirection.OUTBOUND
            or message.status != MessageStatus.QUEUED
        ):
            return message

        message.attempts += 1
        try:
            active_client = client or GupshupClient()
        except WhatsAppNotConfigured as exc:
            _mark_failed(message, exc, status=MessageStatus.SKIPPED)
            return message

        payload = _build_payload(message, active_client)
        message.request_payload = payload
        try:
            data = active_client.send_payload(payload)
        except WhatsAppRetryableError as exc:
            message.error_code = str(exc.code or exc.status_code or "")[:20]
            message.error_message = str(exc)[:2000]
            message.save()
            retry_exc = exc
        except WhatsAppAPIError as exc:
            _mark_failed(message, exc)
            return message
        else:
            message.provider_message_id = extract_message_id(data) or None
            message.status = MessageStatus.SENT
            message.sent_at = timezone.now()
            message.response_payload = data
            message.error_code = ""
            message.error_message = ""
            message.save()
            return message

    # raised outside the atomic block so the attempt counter / error above is committed.
    raise retry_exc


def mark_message_failed(message_id: int, exc: Exception) -> None:
    """Called by the task once retries are exhausted."""
    message = WhatsAppMessage.objects.filter(pk=message_id, status=MessageStatus.QUEUED).first()
    if message is not None:
        _mark_failed(message, exc)


def send_adhoc_message(
    *,
    to: str,
    template_id: str = "",
    body_params: Sequence[str] = (),
    text: str = "",
) -> WhatsAppMessage:
    """
    Send a one-off message synchronously (management command / manual testing).

    """
    message = WhatsAppMessage.objects.create(
        direction=MessageDirection.OUTBOUND,
        phone=normalize_phone(to),
        message_type="text" if text else "template",
        template_id="" if text else template_id,
        body_params=[] if text else [_clean_param(p) for p in body_params],
        text=text,
        event="manual",
    )
    try:
        deliver_message(message.pk)
    except WhatsAppRetryableError as exc:
        mark_message_failed(message.pk, exc)
    message.refresh_from_db()
    return message


def send_otp(phone: str, otp_code: str) -> WhatsAppMessage:
    """
    Send a one-time password through the configured Gupshup OTP (copy-code) template.

    Synchronous — callers are a customer actively waiting for the code.
    """
    return send_adhoc_message(
        to=phone,
        template_id=conf.otp_template_id(),
        body_params=[otp_code],
    )


def retry_messages(messages: Iterable[WhatsAppMessage]) -> int:
    """Re-queue failed / skipped outbound messages (admin action). Returns count re-queued."""
    count = 0
    for message in messages:
        if message.direction != MessageDirection.OUTBOUND or message.status not in (
            MessageStatus.FAILED,
            MessageStatus.SKIPPED,
        ):
            continue
        message.status = MessageStatus.QUEUED
        message.error_code = ""
        message.error_message = ""
        message.failed_at = None
        message.save(
            update_fields=["status", "error_code", "error_message", "failed_at", "updated_at"]
        )
        message_id = message.pk
        transaction.on_commit(lambda message_id=message_id: _enqueue(message_id))
        count += 1
    return count


# --------------------------------------------------------------------------- #
# Inbound (webhook)
# --------------------------------------------------------------------------- #


def _from_timestamp_ms(value: Any) -> datetime:
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=dt_timezone.utc)
    except (TypeError, ValueError):
        return timezone.now()


def handle_status_update(envelope: dict[str, Any]) -> Optional[WhatsAppMessage]:
    """Apply a sent / delivered / read / failed receipt to the matching outbound message.

    ``envelope`` is the full Gupshup webhook envelope: ``{"timestamp", "payload": {...}}``.
    """
    event = envelope.get("payload") or {}
    # Gupshup's correlator: ``gsId`` is our stored provider_message_id on DLR events
    # (sent/delivered/read/async-failed); for enqueued/sync-failed events there is no
    # ``gsId`` and ``id`` itself is the Gupshup message id.
    provider_message_id = event.get("gsId") or event.get("id")
    new_status = event.get("type")
    if not provider_message_id or new_status not in RECEIPT_STATUSES:
        return None

    message = WhatsAppMessage.objects.filter(provider_message_id=provider_message_id).first()
    if message is None:
        return None

    at = _from_timestamp_ms(envelope.get("timestamp"))
    detail = event.get("payload") or {}
    if new_status == MessageStatus.FAILED:
        message.status = MessageStatus.FAILED
        message.failed_at = at
        message.error_code = str(detail.get("code") or "")[:20]
        message.error_message = str(detail.get("reason") or "")[:2000]
    else:
        setattr(message, f"{new_status}_at", getattr(message, f"{new_status}_at") or at)
        if message.status != MessageStatus.FAILED and STATUS_RANK[new_status] > STATUS_RANK.get(
            message.status, 0
        ):
            message.status = new_status
    message.save()
    return message


def _inbound_text(event: dict[str, Any]) -> str:
    msg_type = event.get("type")
    if msg_type == "text":
        return (event.get("payload") or {}).get("text", "")
    return f"[{msg_type}]"


def opt_out_phone(phone: str) -> int:
    """Turn off WhatsApp order updates for customer profiles matching this number."""
    from accounts.models import CustomerProfile

    last10 = re.sub(r"\D", "", phone or "")[-10:]
    if len(last10) < 10:
        return 0

    candidates = CustomerProfile.objects.filter(
        phone__endswith=last10[-2:], notify_via_whatsapp=True
    ).only("pk", "phone")
    ids = [p.pk for p in candidates if re.sub(r"\D", "", p.phone or "")[-10:] == last10]
    if not ids:
        return 0
    return CustomerProfile.objects.filter(pk__in=ids).update(notify_via_whatsapp=False)


def handle_inbound_message(event: dict[str, Any]) -> Optional[WhatsAppMessage]:
    """Log a customer message (Gupshup may redeliver webhooks — deduplicated by message id)."""
    message_id = event.get("id")
    phone = event.get("source") or ""
    if not message_id or not phone:
        return None

    text = _inbound_text(event)
    message, created = WhatsAppMessage.objects.get_or_create(
        provider_message_id=message_id,
        defaults={
            "direction": MessageDirection.INBOUND,
            "phone": phone[:20],
            "message_type": (event.get("type") or "")[:20],
            "text": text,
            "status": MessageStatus.RECEIVED,
            "response_payload": event,
        },
    )
    if created and text.strip().upper() in OPT_OUT_KEYWORDS:
        updated = opt_out_phone(phone)
        logger.info("WhatsApp opt-out from %s — %s profile(s) updated.", phone, updated)
    return message


def process_webhook_payload(payload: dict[str, Any]) -> dict[str, int]:
    """Dispatch one Gupshup webhook envelope. Returns counts (handy for logs / tests)."""
    counts = {"statuses": 0, "messages": 0}
    event_type = payload.get("type")
    if event_type == "message-event":
        if handle_status_update(payload):
            counts["statuses"] += 1
    elif event_type == "message":
        if handle_inbound_message(payload.get("payload") or {}):
            counts["messages"] += 1
    return counts
