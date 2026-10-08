"""Data layer for the checkout app — models only, no business logic."""

from __future__ import annotations

from django.db import models

from core.models import TimeStampedModel


class CheckoutSessionStatus(models.TextChoices):
    """Checkout session lifecycle."""

    DRAFT = "draft", "Draft"
    COMPLETED = "completed", "Completed"


class CheckoutSession(TimeStampedModel):
    """
    DB-backed checkout session (chosen over pure session storage).

    Rationale: supports idempotency_key persistence, links cart + address +
    delivery choices across multi-step HTMX checkout, and survives server
    restarts — unlike ephemeral session dicts alone.
    """

    cart = models.ForeignKey(
        "cart.Cart",
        on_delete=models.CASCADE,
        related_name="checkout_sessions",
        verbose_name="Cart",
    )
    customer_profile = models.ForeignKey(
        "accounts.CustomerProfile",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="checkout_sessions",
        verbose_name="Customer profile",
    )
    session_key = models.CharField(
        max_length=40,
        blank=True,
        db_index=True,
        verbose_name="Session key",
        help_text="Guest session key when customer_profile is null.",
    )
    address = models.ForeignKey(
        "accounts.Address",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checkout_sessions",
        verbose_name="Delivery address",
    )
    delivery_date = models.DateField(null=True, blank=True, verbose_name="Delivery date")

    idempotency_key = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Idempotency key",
    )
    status = models.CharField(
        max_length=20,
        choices=CheckoutSessionStatus.choices,
        default=CheckoutSessionStatus.DRAFT,
        db_index=True,
        verbose_name="Status",
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checkout_sessions",
        verbose_name="Placed order",
    )
    invoice_details = models.JSONField(default=dict, verbose_name="Invoice details")

    class Meta:
        verbose_name = "Checkout session"
        verbose_name_plural = "Checkout sessions"
        indexes = [
            models.Index(fields=["status", "session_key"], name="chk_session_status_idx"),
            models.Index(fields=["idempotency_key"], name="chk_idempotency_key_idx"),
        ]

    def __str__(self) -> str:
        return f"Checkout #{self.pk} ({self.status})"
