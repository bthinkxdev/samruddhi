"""Django admin registrations for the notifications app."""

from __future__ import annotations

from django.contrib import admin

from notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Admin interface for in-app notifications."""

    list_display = ("title", "user", "is_read", "created_at")
    list_filter = ("is_read",)
    search_fields = ("title", "user__email")
    ordering = ("-created_at",)
