"""Notifications application configuration."""

from __future__ import annotations

from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    """Django app config for email, SMS, and WhatsApp notification dispatch."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "notifications"
    verbose_name = "Notifications"

    def ready(self) -> None:
        """Import signal modules when Django starts."""
        import notifications.signals  # noqa: F401
