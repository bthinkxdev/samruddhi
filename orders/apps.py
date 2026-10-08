"""Orders application configuration."""

from __future__ import annotations

from django.apps import AppConfig


class OrdersConfig(AppConfig):
    """Django app config for order lifecycle, status tracking, and order history."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "orders"
    verbose_name = "Orders"

    def ready(self) -> None:
        """Import signal modules when Django starts."""
        import orders.signals  # noqa: F401
