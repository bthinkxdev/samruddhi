"""Dashboard application configuration."""

from __future__ import annotations

from django.apps import AppConfig


class DashboardConfig(AppConfig):
    """Django app config for the operational dashboard."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "dashboard"
    verbose_name = "Dashboard"
