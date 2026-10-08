from django.db import models
from core.models import TimeStampedModel

class DelhiveryShipment(TimeStampedModel):
    """
    Stores Delhivery shipment details and waybill numbers for orders.
    """
    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="delhivery_shipment",
        verbose_name="Order",
    )
    waybill_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Waybill Number",
        help_text="Tracking number provided by Delhivery.",
    )
    tracking_status = models.CharField(
        max_length=100,
        default="Initiated",
        verbose_name="Tracking Status",
        db_index=True,
    )
    label_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name="Label URL",
    )
    pickup_location = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Pickup Location",
        help_text="Delhivery pickup location name used for this shipment.",
    )
    raw_create_response = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Create Shipment Response",
        help_text="Full Delhivery API response from AWB creation.",
    )
    last_status_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Last Status At",
        help_text="Timestamp of the most recent webhook scan event applied.",
    )
    last_event_signature = models.CharField(
        max_length=200,
        blank=True,
        db_index=True,
        verbose_name="Last Event Signature",
        help_text="Dedup key for the most recently applied webhook event.",
    )
    error_message = models.TextField(
        blank=True,
        null=True,
        verbose_name="Error Message / Logs",
    )

    class Meta:
        verbose_name = "Delhivery Shipment"
        verbose_name_plural = "Delhivery Shipments"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Shipment for Order {self.order.order_number} ({self.tracking_status})"
