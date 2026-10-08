"""Recurring schedule application configuration."""

from __future__ import annotations

from django.apps import AppConfig


class RecurringConfig(AppConfig):
    """Shared recurrence engine for corporate orders and subscriptions."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "recurring"
    verbose_name = "Recurring"
    def ready(self) -> None:
        """Register recurrence handlers from domain apps."""
        import accounts.recurrence  # noqa: F401
