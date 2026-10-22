"""Django admin registrations for the WhatsApp app."""

from __future__ import annotations

from django.contrib import admin, messages

from whatsapp.models import WhatsAppMessage, WhatsAppTemplate
from whatsapp.services import retry_messages


@admin.register(WhatsAppTemplate)
class WhatsAppTemplateAdmin(admin.ModelAdmin):
    """Map store events to Gupshup-approved templates."""

    list_display = (
        "event",
        "template_id",
        "body_variables",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active",)
    list_editable = ("is_active",)
    search_fields = ("template_id", "event")


@admin.register(WhatsAppMessage)
class WhatsAppMessageAdmin(admin.ModelAdmin):
    """Read-only audit log of WhatsApp traffic."""

    list_display = (
        "created_at",
        "direction",
        "phone",
        "event",
        "template_id",
        "status",
        "order",
        "attempts",
        "error_code",
    )
    list_filter = ("direction", "status", "event", "message_type")
    search_fields = ("phone", "provider_message_id", "template_id", "order__order_number", "text")
    date_hierarchy = "created_at"
    list_select_related = ("order",)
    actions = ["retry_selected"]
    readonly_fields = [f.name for f in WhatsAppMessage._meta.fields]

    def has_add_permission(self, request) -> bool:
        return False

    @admin.action(description="Retry selected failed/skipped messages")
    def retry_selected(self, request, queryset) -> None:
        count = retry_messages(queryset)
        self.message_user(request, f"{count} message(s) re-queued.", messages.SUCCESS)
