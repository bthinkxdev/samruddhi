"""Django admin registrations for the cart app."""

from __future__ import annotations

from django.contrib import admin

from cart.models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("pk", "customer_profile", "session_key", "coupon_code", "updated_at")
    inlines = [CartItemInline]
