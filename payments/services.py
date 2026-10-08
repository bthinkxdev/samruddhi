"""Write operations and business rules for the payments app."""

from __future__ import annotations

import hashlib
import hmac
import logging
from decimal import InvalidOperation
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import transaction

from payments.models import (
    PaymentStatus,
    PaymentTransaction,
    RazorpayWebhookEvent,
    RazorpayWebhookEventStatus,
)
from payments.registry import get_payment_adapter

if TYPE_CHECKING:
    from orders.models import Order

logger = logging.getLogger(__name__)


@transaction.atomic
def confirm_payment_success(
    *,
    payment_transaction: PaymentTransaction,
    external_transaction_id: str = "",
) -> PaymentTransaction:
    """
    Single convergence point for successful payment — sync or async, browser
    callback or webhook.

    Idempotent and concurrency-safe: reloads the row under select_for_update so
    concurrent callers (browser callback racing the Razorpay webhook, or two
    webhook deliveries) serialize on it. Whichever acquires the lock second sees
    status already SUCCESS and returns without repeating the order transition,
    cart clearing, or confirmation email.

    ``external_transaction_id``, if given, is recorded as part of this exact
    confirmation only — never applied once the transaction is already SUCCESS,
    so a late or duplicate event carrying a *different* payment id (e.g. a
    stale retry, or a second attempt against the same Razorpay order) can't
    silently overwrite the id that actually triggered confirmation.
    """
    payment_transaction = PaymentTransaction.objects.select_for_update().get(pk=payment_transaction.pk)
    if payment_transaction.status == PaymentStatus.SUCCESS:
        return payment_transaction

    update_fields = ["status", "updated_at"]
    payment_transaction.status = PaymentStatus.SUCCESS
    if external_transaction_id:
        payment_transaction.external_transaction_id = external_transaction_id
        update_fields.append("external_transaction_id")
    payment_transaction.save(update_fields=update_fields)

    #empty and deactivate the cart now that payment is confirmed
    order = payment_transaction.order
    if order:
        from checkout.models import CheckoutSession, CheckoutSessionStatus
        session = CheckoutSession.objects.filter(order=order).first()
        if session:
            session.status = CheckoutSessionStatus.COMPLETED
            session.save(update_fields=["status", "updated_at"])

        if order.cart:
            cart = order.cart
            from cart.models import CartItem
            CartItem.objects.filter(cart=cart).delete()

        # auto confirm order once online payment succeeds (COD is confirmed manually by an admin)
        from orders.models import OrderStatus
        from orders.services import transition_order_status
        if payment_transaction.gateway_key != "cod" and order.order_status == OrderStatus.CHECKOUT_PENDING:
            transition_order_status(order=order, new_status=OrderStatus.CONFIRMED, note="Payment successful", force=True)

        #send order placement confirmation email
        from notifications.tasks import dispatch_order_confirmation_notification
        transaction.on_commit(
            lambda: dispatch_order_confirmation_notification.delay(order_id=order.pk)
        )

    return payment_transaction


@transaction.atomic
def confirm_payment_failed(*, payment_transaction: PaymentTransaction) -> PaymentTransaction:
    """
    Mark a payment transaction as failed.

    Idempotent and concurrency-safe like confirm_payment_success. Never
    downgrades an already-SUCCESS transaction — a late or stale payment.failed
    event must not undo a payment that already succeeded.
    """
    payment_transaction = PaymentTransaction.objects.select_for_update().get(pk=payment_transaction.pk)
    if payment_transaction.status in (PaymentStatus.SUCCESS, PaymentStatus.FAILED):
        return payment_transaction

    payment_transaction.status = PaymentStatus.FAILED
    payment_transaction.save(update_fields=["status", "updated_at"])
    return payment_transaction


@transaction.atomic
def process_payment(
    *,
    order: Order,
    gateway_key: str,
    payment_data: dict[str, Any],
) -> PaymentTransaction:
    """
    Process payment via registry-selected adapter.

    Writes PaymentTransaction as PENDING immediately. Sync gateways capture
    inline; async gateways complete via webhook → confirm_payment_success.
    """
    adapter = get_payment_adapter(gateway_key=gateway_key)
    metadata = {"order_id": order.pk, "order_number": order.order_number, **payment_data}

    #clean up: mark any previous abandoned payment attempts as failed
    PaymentTransaction.objects.filter(
        order=order,
        status=PaymentStatus.PENDING
    ).update(status=PaymentStatus.FAILED)

    payment_tx = PaymentTransaction.objects.create(
        order=order,
        gateway_key=gateway_key,
        amount=order.total_amount,
        currency=order.currency,
        status=PaymentStatus.PENDING,
        metadata=metadata,
    )

    intent = adapter.create_payment_intent(
        amount=order.total_amount,
        currency=order.currency.code,
        metadata=metadata,
    )
    payment_tx.external_intent_id = intent.intent_id
    payment_tx.save(update_fields=["external_intent_id", "updated_at"])

    if adapter.is_async:
        return payment_tx

    capture = adapter.capture(intent_id=intent.intent_id)

    payment_tx.external_transaction_id = capture.transaction_id
    payment_tx.metadata.update(capture.metadata)
    payment_tx.save(update_fields=["external_transaction_id", "metadata", "updated_at"])

    if capture.success:
        confirm_payment_success(payment_transaction=payment_tx)
        #COD checkouts are successful, but the payment itself should remain Pending until the admin manually collects the cash and marks it as Success.
        if gateway_key == "cod":
            payment_tx.status = PaymentStatus.PENDING
            payment_tx.save(update_fields=["status", "updated_at"])
    else:
        confirm_payment_failed(payment_transaction=payment_tx)

    return payment_tx


@transaction.atomic
def handle_payment_webhook(
    *,
    gateway_key: str,
    payload: bytes,
    signature: str,
) -> PaymentTransaction | None:
    """
    Verify webhook via adapter and converge on confirm_payment_success/failed.
    """
    adapter = get_payment_adapter(gateway_key=gateway_key)
    event = adapter.verify_webhook(payload=payload, signature=signature)

    intent_id = event.get("intent_id", "")
    payment_tx = PaymentTransaction.objects.filter(
        external_intent_id=intent_id,
        gateway_key=gateway_key,
    ).first()
    if payment_tx is None:
        return None

    if event.get("status") == "success":
        return confirm_payment_success(
            payment_transaction=payment_tx,
            external_transaction_id=event.get("transaction_id", ""),
        )

    return confirm_payment_failed(payment_transaction=payment_tx)


def verify_razorpay_webhook_signature(*, payload: bytes, signature: str) -> bool:
    """
    Verify a real Razorpay webhook's ``X-Razorpay-Signature`` header.

    Signature = hex(HMAC-SHA256(raw_body, RAZORPAY_WEBHOOK_SECRET)). Must be
    computed over the raw request body exactly as received — never re-serialize
    parsed JSON before calling this. Returns False (never raises) if the secret
    or signature is missing, so callers can log and reject cleanly.
    """
    secret = settings.RAZORPAY_WEBHOOK_SECRET
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


_RAZORPAY_HANDLED_EVENTS = frozenset({"payment.captured", "order.paid", "payment.failed"})


@transaction.atomic
def handle_razorpay_webhook_event(
    *,
    event_id: str,
    event_type: str,
    event_data: dict[str, Any],
) -> tuple[RazorpayWebhookEvent, bool]:
    """
    Idempotent entry point for real, signature-verified Razorpay webhook events.

    Caller must verify the signature (verify_razorpay_webhook_signature) before
    calling this. Three independent layers protect confirmation:

    1. ``event_id`` uniqueness (this function) — catches Razorpay redelivering
       the exact same event.
    2. The PaymentTransaction status guard in confirm_payment_success/failed —
       catches Razorpay firing *different* events (payment.captured and
       order.paid commonly both fire) for the same underlying payment.
    3. The payment-id integrity check below — if the transaction already
       recorded a *different* Razorpay payment id, the incoming event is
       rejected as PAYMENT_ID_MISMATCH rather than silently ignored or, worse,
       allowed to overwrite the id that actually confirmed the order.

    Never confirms an order it cannot positively identify and validate: a
    missing payment id, an unresolvable transaction, an amount/currency
    mismatch, or a conflicting payment id is recorded on RazorpayWebhookEvent
    for investigation and acknowledged, but never guessed at or discarded.

    Returns (event_record, created) — ``created`` is False for a redelivery of
    an event_id already on file, in which case no side effects run at all.
    """
    try:
        payment_entity = (event_data.get("payload") or {}).get("payment", {}).get("entity", {}) or {}
    except AttributeError:
        payment_entity = {}

    razorpay_order_id = str(payment_entity.get("order_id") or "")
    razorpay_payment_id = str(payment_entity.get("id") or "")
    amount_paise = payment_entity.get("amount")
    currency_code = str(payment_entity.get("currency") or "")
    entity_status = str(payment_entity.get("status") or "")

    event, created = RazorpayWebhookEvent.objects.get_or_create(
        event_id=event_id,
        defaults={
            "event_type": event_type,
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "payload": event_data,
            "status": RazorpayWebhookEventStatus.ERROR,
        },
    )
    if not created:
        logger.info("Ignoring duplicate Razorpay webhook delivery: event_id=%s", event_id)
        return event, False

    if event_type not in _RAZORPAY_HANDLED_EVENTS:
        event.status = RazorpayWebhookEventStatus.IGNORED_EVENT_TYPE
        event.save(update_fields=["status", "updated_at"])
        return event, True

    #payment.captured/order.paid must positively identify the payment before we
    #ever consider confirming an order from it — a missing payment id is the
    #one field we can least afford to guess at.
    if event_type in ("payment.captured", "order.paid"):
        required_present = razorpay_order_id and razorpay_payment_id and amount_paise is not None and currency_code and entity_status
    else:
        required_present = razorpay_order_id and amount_paise is not None

    if not required_present:
        logger.error(
            "Malformed/incomplete Razorpay webhook payload: event_id=%s event_type=%s "
            "has_order_id=%s has_payment_id=%s has_amount=%s has_currency=%s has_status=%s",
            event_id, event_type,
            bool(razorpay_order_id), bool(razorpay_payment_id), amount_paise is not None,
            bool(currency_code), bool(entity_status),
        )
        event.save(update_fields=["status", "updated_at"])
        return event, True

    try:
        received_amount_paise = int(amount_paise)
    except (TypeError, ValueError):
        logger.error(
            "Non-numeric amount in Razorpay webhook: event_id=%s event_type=%s amount=%r",
            event_id, event_type, amount_paise,
        )
        event.save(update_fields=["status", "updated_at"])
        return event, True

    payment_tx = (
        PaymentTransaction.objects.filter(
            external_intent_id=razorpay_order_id,
            gateway_key__startswith="razorpay",
        )
        .select_related("currency", "order")
        .first()
    )
    if payment_tx is None:
        logger.warning(
            "Unknown Razorpay transaction for webhook: event_id=%s event_type=%s "
            "razorpay_order_id=%s razorpay_payment_id=%s",
            event_id, event_type, razorpay_order_id, razorpay_payment_id,
        )
        event.status = RazorpayWebhookEventStatus.UNKNOWN_TRANSACTION
        event.save(update_fields=["status", "updated_at"])
        return event, True

    try:
        expected_amount_paise = int((payment_tx.amount * 100).to_integral_value())
    except (InvalidOperation, TypeError):
        expected_amount_paise = None

    if expected_amount_paise is None or received_amount_paise != expected_amount_paise:
        logger.error(
            "Razorpay webhook amount mismatch: event_id=%s payment_transaction_id=%s "
            "expected_paise=%s received_paise=%s",
            event_id, payment_tx.pk, expected_amount_paise, received_amount_paise,
        )
        event.status = RazorpayWebhookEventStatus.AMOUNT_MISMATCH
        event.payment_transaction = payment_tx
        event.save(update_fields=["status", "payment_transaction", "updated_at"])
        return event, True

    expected_currency = (payment_tx.currency.code or "").upper()
    if currency_code.upper() != expected_currency:
        logger.error(
            "Razorpay webhook currency mismatch: event_id=%s payment_transaction_id=%s "
            "expected=%s received=%s",
            event_id, payment_tx.pk, expected_currency, currency_code,
        )
        event.status = RazorpayWebhookEventStatus.CURRENCY_MISMATCH
        event.payment_transaction = payment_tx
        event.save(update_fields=["status", "payment_transaction", "updated_at"])
        return event, True

    if event_type in ("payment.captured", "order.paid"):
        if entity_status != "captured":
            logger.error(
                "Razorpay webhook payment.status not captured: event_id=%s "
                "payment_transaction_id=%s status=%s",
                event_id, payment_tx.pk, entity_status,
            )
            event.status = RazorpayWebhookEventStatus.ERROR
            event.payment_transaction = payment_tx
            event.save(update_fields=["status", "payment_transaction", "updated_at"])
            return event, True

        #payment ID integrity: an already-recorded, DIFFERENT payment id means
        #two distinct Razorpay payments claim the same order — never overwrite
        #the one that actually confirmed it, and never confirm on the strength
        #of the newcomer. Recorded as its own outcome so it surfaces for
        #investigation rather than blending into an ordinary PROCESSED event.
        existing_transaction_id = payment_tx.external_transaction_id
        if existing_transaction_id and existing_transaction_id != razorpay_payment_id:
            logger.error(
                "Razorpay webhook payment ID mismatch: event_id=%s payment_transaction_id=%s "
                "existing_payment_id=%s incoming_payment_id=%s",
                event_id, payment_tx.pk, existing_transaction_id, razorpay_payment_id,
            )
            event.status = RazorpayWebhookEventStatus.PAYMENT_ID_MISMATCH
            event.payment_transaction = payment_tx
            event.save(update_fields=["status", "payment_transaction", "updated_at"])
            return event, True

        confirm_payment_success(
            payment_transaction=payment_tx,
            external_transaction_id=razorpay_payment_id,
        )
    else:
        confirm_payment_failed(payment_transaction=payment_tx)

    event.status = RazorpayWebhookEventStatus.PROCESSED
    event.payment_transaction = payment_tx
    event.save(update_fields=["status", "payment_transaction", "updated_at"])
    return event, True
