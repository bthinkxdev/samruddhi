"""Reports application configuration."""

from __future__ import annotations

from django.apps import AppConfig


class ReportsConfig(AppConfig):
    """Django app config for analytics dashboards and aggregated reporting."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "reports"
    verbose_name = "Reports"

    def ready(self) -> None:
        """Import signal modules when Django starts."""
        import reports.signals  # noqa: F401
