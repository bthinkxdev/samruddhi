"""Marketing application configuration."""

from __future__ import annotations

from django.apps import AppConfig


class MarketingConfig(AppConfig):
    """Django app config for promotions, coupons, and campaign management."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "marketing"
    verbose_name = "Marketing"

    def ready(self) -> None:
        """Import signal modules when Django starts."""
        import marketing.signals  # noqa: F401
