"""Django admin registrations for the checkout app."""

from __future__ import annotations

from django.contrib import admin

from checkout.models import CheckoutSession


@admin.register(CheckoutSession)
class CheckoutSessionAdmin(admin.ModelAdmin):
    list_display = ("pk", "cart", "status", "idempotency_key", "order", "created_at")
