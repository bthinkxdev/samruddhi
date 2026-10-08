"""Delivery application configuration."""

from __future__ import annotations

from django.apps import AppConfig


class DeliveryConfig(AppConfig):
    """Django app config for delivery zones, slots, and fulfillment logistics."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "delivery"
    verbose_name = "Delivery"

    def ready(self) -> None:
        """Import signal modules when Django starts."""
        import delivery.signals  # noqa: F401
