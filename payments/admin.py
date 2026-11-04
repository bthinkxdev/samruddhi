"""Django admin registrations for the payments app."""

from __future__ import annotations

from django.contrib import admin

from payments.models import PaymentTransaction, RazorpayWebhookEvent, StripeWebhookEvent


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ("pk", "order", "gateway_key", "amount", "status", "created_at")


class _ReadOnlyWebhookEventAdmin(admin.ModelAdmin):
    """Shared read-only behavior for gateway webhook audit logs."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StripeWebhookEvent)
class StripeWebhookEventAdmin(_ReadOnlyWebhookEventAdmin):
    """Read-only audit log — investigate unknown/mismatched webhook events here."""

    list_display = (
        "event_id",
        "event_type",
        "status",
        "checkout_session_id",
        "payment_intent_id",
        "payment_transaction",
        "created_at",
    )
    list_filter = ("status", "event_type")
    search_fields = ("event_id", "checkout_session_id", "payment_intent_id")
    readonly_fields = [f.name for f in StripeWebhookEvent._meta.fields]


@admin.register(RazorpayWebhookEvent)
class RazorpayWebhookEventAdmin(_ReadOnlyWebhookEventAdmin):
    """Historical audit log from the retired Razorpay integration — read-only."""

    list_display = (
        "event_id",
        "event_type",
        "status",
        "razorpay_order_id",
        "razorpay_payment_id",
        "payment_transaction",
        "created_at",
    )
    list_filter = ("status", "event_type")
    search_fields = ("event_id", "razorpay_order_id", "razorpay_payment_id")
    readonly_fields = [f.name for f in RazorpayWebhookEvent._meta.fields]
