"""Cms application configuration."""

from __future__ import annotations

from django.apps import AppConfig


class CmsConfig(AppConfig):
    """Django app config for CMS pages, banners, and editorial content."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "cms"
    verbose_name = "CMS"

    def ready(self) -> None:
        """Import signal modules when Django starts."""
        import cms.signals  # noqa: F401
