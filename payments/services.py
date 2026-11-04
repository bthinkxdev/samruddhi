"""Write operations and business rules for the payments app."""

from __future__ import annotations

import logging
from decimal import InvalidOperation
from typing import TYPE_CHECKING, Any

from django.db import transaction

from payments.models import (
    PaymentStatus,
    PaymentTransaction,
    StripeWebhookEvent,
    StripeWebhookEventStatus,
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
    concurrent callers (the browser return view racing the gateway's webhook, or
    two webhook deliveries) serialize on it. Whichever acquires the lock second
    sees status already SUCCESS and returns without repeating the order
    transition, cart clearing, or confirmation email.

    ``external_transaction_id``, if given, is recorded as part of this exact
    confirmation only — never applied once the transaction is already SUCCESS,
    so a late or duplicate event carrying a *different* payment id (e.g. a
    stale retry, or a second attempt against the same payment) can't silently
    overwrite the id that actually triggered confirmation.
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


_STRIPE_HANDLED_EVENTS = frozenset(
    {
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
        "checkout.session.async_payment_failed",
        "payment_intent.payment_failed",
    }
)

_STRIPE_SUCCESS_EVENTS = frozenset({"checkout.session.completed", "checkout.session.async_payment_succeeded"})


@transaction.atomic
def handle_stripe_webhook_event(
    *,
    event_id: str,
    event_type: str,
    event_data: dict[str, Any],
) -> tuple[StripeWebhookEvent, bool]:
    """
    Idempotent entry point for real, signature-verified Stripe webhook events.

    Caller must verify the signature (via the Stripe adapter's
    ``verify_webhook``, which uses the official SDK) before calling this.
    Mirrors the guarantees the old Razorpay webhook handler had:

    1. ``event_id`` uniqueness (this function) — catches Stripe redelivering
       the exact same event.
    2. The PaymentTransaction status guard in confirm_payment_success/failed —
       catches a webhook event racing the browser return-view's own
       confirmation of the same payment.
    3. The PaymentIntent-id integrity check below — if the transaction already
       recorded a *different* Stripe PaymentIntent id, the incoming event is
       rejected as INTENT_ID_MISMATCH rather than silently ignored or, worse,
       allowed to overwrite the id that actually confirmed the order.

    Never confirms an order it cannot positively identify and validate: a
    missing id, an unresolvable transaction, an amount/currency mismatch, or a
    conflicting PaymentIntent id is recorded on StripeWebhookEvent for
    investigation and acknowledged, but never guessed at or discarded.

    Returns (event_record, created) — ``created`` is False for a redelivery of
    an event_id already on file, in which case no side effects run at all.
    """
    try:
        obj = (event_data.get("data") or {}).get("object") or {}
    except AttributeError:
        obj = {}

    #checkout.session.* events carry a Checkout Session as their object (its
    #``id`` is what we stored as PaymentTransaction.external_intent_id);
    #payment_intent.payment_failed carries a PaymentIntent instead (no session
    #id on it at all — we identify the transaction via the order_id we embed
    #in the PaymentIntent's own metadata at creation time).
    is_session_event = event_type.startswith("checkout.session.")
    session_id = str(obj.get("id") or "") if is_session_event else ""
    payment_intent_id = str(obj.get("payment_intent") or "") if is_session_event else str(obj.get("id") or "")
    amount_minor = obj.get("amount_total") if is_session_event else obj.get("amount")
    currency_code = str(obj.get("currency") or "")
    payment_status = str(obj.get("payment_status") or "")
    order_id_meta = str((obj.get("metadata") or {}).get("order_id") or "")

    event, created = StripeWebhookEvent.objects.get_or_create(
        event_id=event_id,
        defaults={
            "event_type": event_type,
            "checkout_session_id": session_id,
            "payment_intent_id": payment_intent_id,
            "payload": event_data,
            "status": StripeWebhookEventStatus.ERROR,
        },
    )
    if not created:
        logger.info("Ignoring duplicate Stripe webhook delivery: event_id=%s", event_id)
        return event, False

    if event_type not in _STRIPE_HANDLED_EVENTS:
        event.status = StripeWebhookEventStatus.IGNORED_EVENT_TYPE
        event.save(update_fields=["status", "updated_at"])
        return event, True

    if is_session_event:
        required_present = session_id and amount_minor is not None and currency_code
    else:
        required_present = payment_intent_id and order_id_meta and amount_minor is not None and currency_code

    if not required_present:
        logger.error(
            "Malformed/incomplete Stripe webhook payload: event_id=%s event_type=%s "
            "has_session_id=%s has_payment_intent=%s has_order_id=%s has_amount=%s has_currency=%s",
            event_id, event_type, bool(session_id), bool(payment_intent_id),
            bool(order_id_meta), amount_minor is not None, bool(currency_code),
        )
        event.save(update_fields=["status", "updated_at"])
        return event, True

    try:
        received_amount_minor = int(amount_minor)
    except (TypeError, ValueError):
        logger.error(
            "Non-numeric amount in Stripe webhook: event_id=%s event_type=%s amount=%r",
            event_id, event_type, amount_minor,
        )
        event.save(update_fields=["status", "updated_at"])
        return event, True

    if is_session_event:
        payment_tx = (
            PaymentTransaction.objects.filter(external_intent_id=session_id, gateway_key="stripe")
            .select_related("currency", "order")
            .first()
        )
    else:
        payment_tx = (
            PaymentTransaction.objects.filter(order_id=order_id_meta, gateway_key="stripe")
            .select_related("currency", "order")
            .order_by("-created_at")
            .first()
        )

    if payment_tx is None:
        logger.warning(
            "Unknown Stripe transaction for webhook: event_id=%s event_type=%s "
            "session_id=%s payment_intent_id=%s order_id_meta=%s",
            event_id, event_type, session_id, payment_intent_id, order_id_meta,
        )
        event.status = StripeWebhookEventStatus.UNKNOWN_TRANSACTION
        event.save(update_fields=["status", "updated_at"])
        return event, True

    try:
        expected_amount_minor = int((payment_tx.amount * 100).to_integral_value())
    except (InvalidOperation, TypeError):
        expected_amount_minor = None

    if expected_amount_minor is None or received_amount_minor != expected_amount_minor:
        logger.error(
            "Stripe webhook amount mismatch: event_id=%s payment_transaction_id=%s "
            "expected_minor=%s received_minor=%s",
            event_id, payment_tx.pk, expected_amount_minor, received_amount_minor,
        )
        event.status = StripeWebhookEventStatus.AMOUNT_MISMATCH
        event.payment_transaction = payment_tx
        event.save(update_fields=["status", "payment_transaction", "updated_at"])
        return event, True

    expected_currency = (payment_tx.currency.code or "").upper()
    if currency_code.upper() != expected_currency:
        logger.error(
            "Stripe webhook currency mismatch: event_id=%s payment_transaction_id=%s "
            "expected=%s received=%s",
            event_id, payment_tx.pk, expected_currency, currency_code,
        )
        event.status = StripeWebhookEventStatus.CURRENCY_MISMATCH
        event.payment_transaction = payment_tx
        event.save(update_fields=["status", "payment_transaction", "updated_at"])
        return event, True

    if event_type in _STRIPE_SUCCESS_EVENTS:
        if is_session_event and payment_status not in ("paid", "no_payment_required"):
            #checkout.session.completed can fire for an async payment method
            #before it has actually settled — only a paid (or
            #no-payment-required) session confirms the order; anything else
            #waits for async_payment_succeeded/async_payment_failed.
            event.status = StripeWebhookEventStatus.ERROR
            event.payment_transaction = payment_tx
            event.save(update_fields=["status", "payment_transaction", "updated_at"])
            return event, True

        #PaymentIntent-id integrity: an already-recorded, DIFFERENT intent id
        #means two distinct Stripe payments claim the same order — never
        #overwrite the one that actually confirmed it, and never confirm on
        #the strength of the newcomer.
        existing_intent_id = payment_tx.external_transaction_id
        if existing_intent_id and payment_intent_id and existing_intent_id != payment_intent_id:
            logger.error(
                "Stripe webhook PaymentIntent mismatch: event_id=%s payment_transaction_id=%s "
                "existing_intent_id=%s incoming_intent_id=%s",
                event_id, payment_tx.pk, existing_intent_id, payment_intent_id,
            )
            event.status = StripeWebhookEventStatus.INTENT_ID_MISMATCH
            event.payment_transaction = payment_tx
            event.save(update_fields=["status", "payment_transaction", "updated_at"])
            return event, True

        confirm_payment_success(payment_transaction=payment_tx, external_transaction_id=payment_intent_id)
    else:
        confirm_payment_failed(payment_transaction=payment_tx)

    event.status = StripeWebhookEventStatus.PROCESSED
    event.payment_transaction = payment_tx
    event.save(update_fields=["status", "payment_transaction", "updated_at"])
    return event, True
