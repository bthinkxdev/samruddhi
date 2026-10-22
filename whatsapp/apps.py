"""WhatsApp application configuration."""

from __future__ import annotations

from django.apps import AppConfig


class WhatsappConfig(AppConfig):
    """Django app config for the Gupshup WhatsApp Business API integration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "whatsapp"
    verbose_name = "WhatsApp"
