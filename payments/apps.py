"""Payments application configuration."""

from __future__ import annotations

from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    """Django app config for payment gateway integration and transaction records."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "payments"
    verbose_name = "Payments"

    def ready(self) -> None:
        """Import signal modules when Django starts."""
        import payments.signals  # noqa: F401
