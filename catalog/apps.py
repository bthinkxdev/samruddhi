"""Catalog application configuration."""

from __future__ import annotations

from django.apps import AppConfig


class CatalogConfig(AppConfig):
    """Django app config for product catalog, categories, and inventory."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "catalog"
    verbose_name = "Catalog"

    def ready(self) -> None:
        """Import signal modules when Django starts."""
        import catalog.signals  # noqa: F401
