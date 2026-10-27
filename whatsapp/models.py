"""Data layer for the WhatsApp app — models only, no business logic."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from core.models import TimeStampedModel

# event fired right after an order is placed (online payment captured or COD placed).
# every other event key is an orders.models.OrderStatus value.
EVENT_ORDER_PLACED = "order_placed"

TEMPLATE_VARIABLES: dict[str, str] = {
    "customer_name": "Customer first name",
    "order_number": "Order number",
    "store_name": "Store name",
    "order_total": "Order total with currency",
    "order_status": "Order status label",
    "order_items": "First few product names",
}


def event_choices() -> list[tuple[str, str]]:
    """
    Callable choices (Django 5) so adding an OrderStatus never needs a new migration here.
    """
    from orders.models import OrderStatus

    return [(EVENT_ORDER_PLACED, "Order placed (confirmation)")] + [
        (value, f"Status → {label}") for value, label in OrderStatus.choices
    ]


def variable_choices() -> list[tuple[str, str]]:
    return [("", "— none —")] + list(TEMPLATE_VARIABLES.items())


class WhatsAppTemplate(TimeStampedModel):
    """
    Maps a store event to a Gupshup-approved WhatsApp message template.

    """

    event = models.CharField(
        max_length=40,
        unique=True,
        choices=event_choices,
        verbose_name="Event",
        help_text="Store event that sends this template.",
    )
    template_id = models.CharField(
        max_length=512,
        verbose_name="Gupshup template ID",
        help_text="Template UUID exactly as approved in the Gupshup dashboard.",
    )
    body_variables = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Body variables",
        help_text=(
            "Ordered list filling {{1}}, {{2}}, ... e.g. "
            '["customer_name", "order_number", "store_name"]. Allowed: '
            + ", ".join(TEMPLATE_VARIABLES)
        ),
    )
    button_url_variable = models.CharField(
        max_length=40,
        blank=True,
        choices=variable_choices,
        verbose_name="URL button variable",
        help_text="Only if the template has a dynamic URL button — fills its {{1}} suffix.",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Active",
        help_text="Untick to stop sending this event without deleting the mapping.",
    )

    class Meta:
        verbose_name = "WhatsApp template"
        verbose_name_plural = "WhatsApp templates"
        ordering = ["event"]

    def __str__(self) -> str:
        return f"{self.get_event_display()} → {self.template_id}"

    def clean(self) -> None:
        super().clean()
        if not isinstance(self.body_variables, list):
            raise ValidationError({"body_variables": "Must be a JSON list of variable names."})
        unknown = [v for v in self.body_variables if v not in TEMPLATE_VARIABLES]
        if unknown:
            raise ValidationError(
                {"body_variables": f"Unknown variable(s): {', '.join(map(str, unknown))}."}
            )


class MessageDirection(models.TextChoices):
    OUTBOUND = "outbound", "Outbound"
    INBOUND = "inbound", "Inbound"


class MessageStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    SENT = "sent", "Sent"
    DELIVERED = "delivered", "Delivered"
    READ = "read", "Read"
    FAILED = "failed", "Failed"
    SKIPPED = "skipped", "Skipped"
    RECEIVED = "received", "Received"


class WhatsAppMessage(TimeStampedModel):
    """Audit log of every WhatsApp message sent or received."""

    direction = models.CharField(
        max_length=10,
        choices=MessageDirection.choices,
        default=MessageDirection.OUTBOUND,
        db_index=True,
    )
    phone = models.CharField(
        max_length=20,
        db_index=True,
        verbose_name="Phone",
        help_text="Customer number in international format, digits only (e.g. 919876543210).",
    )
    event = models.CharField(max_length=40, blank=True, db_index=True)
    message_type = models.CharField(max_length=20, default="template")
    template_id = models.CharField(max_length=512, blank=True)
    body_params = models.JSONField(default=list, blank=True)
    button_url_param = models.CharField(max_length=255, blank=True)
    text = models.TextField(blank=True, help_text="Free-text body (text messages / inbound).")
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="whatsapp_messages",
    )
    status = models.CharField(
        max_length=12,
        choices=MessageStatus.choices,
        default=MessageStatus.QUEUED,
        db_index=True,
    )
    provider_message_id = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        verbose_name="Gupshup message id",
        help_text="Gupshup's messageId, returned on submit and used to correlate webhook events.",
    )
    idempotency_key = models.CharField(
        max_length=120,
        unique=True,
        null=True,
        blank=True,
        help_text="Prevents the same order event being sent twice (e.g. on task retries).",
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    error_code = models.CharField(max_length=20, blank=True)
    error_message = models.TextField(blank=True)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "WhatsApp message"
        verbose_name_plural = "WhatsApp messages"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="whatsapp_msg_status_idx"),
        ]

    def __str__(self) -> str:
        label = self.template_id or self.message_type
        return f"{self.get_direction_display()} {label} → {self.phone} ({self.status})"
