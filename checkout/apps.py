"""Checkout application configuration."""

from __future__ import annotations

from django.apps import AppConfig


class CheckoutConfig(AppConfig):
    """Django app config for checkout flow, delivery slot selection, and order preview."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "checkout"
    verbose_name = "Checkout"

    def ready(self) -> None:
        """Import signal modules when Django starts."""
        import checkout.signals  # noqa: F401
