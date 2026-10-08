"""Accounts application configuration."""

from __future__ import annotations

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Django app config for user authentication, profiles, and address book."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Accounts"

    def ready(self) -> None:
        """Import signal modules when Django starts."""
        import accounts.signals  # noqa: F401
