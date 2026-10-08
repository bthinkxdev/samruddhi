"""Data layer for the payments app — models only, no business logic."""

from __future__ import annotations

from django.db import models

from core.models import TimeStampedModel


class PaymentStatus(models.TextChoices):
    """Payment transaction lifecycle."""

    PENDING = "pending", "Pending"
    SUCCESS = "success", "Success"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    REFUNDED = "refunded", "Refunded"


class PaymentTransaction(TimeStampedModel):
    """Record of a payment attempt for an order."""

    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="payment_transactions",
        verbose_name="Order",
    )
    gateway_key = models.CharField(max_length=40, db_index=True, verbose_name="Gateway key")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Amount")
    currency = models.ForeignKey(
        "core.Currency",
        on_delete=models.PROTECT,
        related_name="payment_transactions",
        verbose_name="Currency",
    )
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        db_index=True,
        verbose_name="Status",
    )
    external_intent_id = models.CharField(
        max_length=120,
        blank=True,
        db_index=True,
        verbose_name="External intent ID",
    )
    external_transaction_id = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="External transaction ID",
    )
    metadata = models.JSONField(default=dict, verbose_name="Metadata")

    class Meta:
        verbose_name = "Payment transaction"
        verbose_name_plural = "Payment transactions"
        indexes = [
            models.Index(fields=["order", "status"], name="pay_tx_order_status_idx"),
            models.Index(fields=["gateway_key", "status"], name="pay_tx_gateway_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.gateway_key} {self.amount} ({self.status})"


class RazorpayWebhookEventStatus(models.TextChoices):
    """
    Terminal outcome of the first time an event_id was processed.

    Deliberately has no "duplicate" member: a redelivery is a runtime fact
    (get_or_create's ``created`` flag), not something that should overwrite the
    original outcome recorded here.
    """

    PROCESSED = "processed", "Processed"
    UNKNOWN_TRANSACTION = "unknown_transaction", "Unknown transaction"
    AMOUNT_MISMATCH = "amount_mismatch", "Amount mismatch"
    CURRENCY_MISMATCH = "currency_mismatch", "Currency mismatch"
    PAYMENT_ID_MISMATCH = "payment_id_mismatch", "Payment ID mismatch"
    IGNORED_EVENT_TYPE = "ignored_event_type", "Ignored event type"
    ERROR = "error", "Error"


class RazorpayWebhookEvent(TimeStampedModel):
    """
    Durable, DB-backed dedup + audit record for one Razorpay webhook delivery.

    ``event_id`` (from the ``X-Razorpay-Event-Id`` header) is unique per event —
    this is the permanent idempotency gate for webhook retries, independent of
    the PaymentTransaction-level status guard in payments.services which handles
    the separate case of two *different* event_ids (e.g. payment.captured and
    order.paid) referring to the same payment.
    """

    event_id = models.CharField(max_length=80, unique=True, db_index=True, verbose_name="Razorpay event ID")
    event_type = models.CharField(max_length=60, db_index=True, verbose_name="Event type")
    razorpay_order_id = models.CharField(max_length=120, blank=True, db_index=True, verbose_name="Razorpay order ID")
    razorpay_payment_id = models.CharField(max_length=120, blank=True, verbose_name="Razorpay payment ID")
    payload = models.JSONField(default=dict, verbose_name="Payload")
    payment_transaction = models.ForeignKey(
        PaymentTransaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="razorpay_webhook_events",
        verbose_name="Payment transaction",
    )
    status = models.CharField(
        max_length=24,
        choices=RazorpayWebhookEventStatus.choices,
        db_index=True,
        verbose_name="Status",
    )

    class Meta:
        verbose_name = "Razorpay webhook event"
        verbose_name_plural = "Razorpay webhook events"

    def __str__(self) -> str:
        return f"{self.event_type} {self.event_id} ({self.status})"
