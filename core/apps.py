"""Core application configuration."""

from __future__ import annotations

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Django app config for shared mixins, currency, and platform utilities."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Core"

    def ready(self) -> None:
        """Import signal modules when Django starts."""
        import core.signals  # noqa: F401
