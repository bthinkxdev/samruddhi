"""Django admin registrations for the orders app."""

from __future__ import annotations

from django.contrib import admin

from orders.models import Order, OrderItem, OrderStatusHistory, ProofOfDelivery
from orders.services import transition_order_status


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ("from_status", "to_status", "changed_by", "changed_at", "note")
    can_delete = False

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "customer_profile",
        "order_status",
        "total_amount",
        "created_at",
    )
    list_filter = ("order_status",)
    inlines = [OrderItemInline, OrderStatusHistoryInline]

    def save_model(self, request, obj, form, change) -> None:
        if change:
            existing = Order.objects.filter(pk=obj.pk).first()
            if existing and existing.order_status != obj.order_status:
                transition_order_status(
                    order=existing,
                    new_status=obj.order_status,
                    actor=request.user,
                    note="Updated via Django admin.",
                )
                return
        super().save_model(request, obj, form, change)


@admin.register(ProofOfDelivery)
class ProofOfDeliveryAdmin(admin.ModelAdmin):
    list_display = ("order", "recipient_name", "delivered_at")
