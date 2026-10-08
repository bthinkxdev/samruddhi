"""Cart application configuration."""

from __future__ import annotations

from django.apps import AppConfig


class CartConfig(AppConfig):
    """Django app config for shopping cart session and line-item management."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "cart"
    verbose_name = "Cart"

    def ready(self) -> None:
        """Import signal modules when Django starts."""
        import cart.signals  # noqa: F401
