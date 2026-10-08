"""Django admin registrations for the accounts app."""

from __future__ import annotations

from django.contrib import admin

from accounts.models import (
    Address,
    CustomerProfile,
    OTPRequest,
    SavedPaymentMethod,
    Subscription,
    Wishlist,
    WishlistItem,
)


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    """Admin interface for customer profiles."""

    list_display = ("user", "phone", "phone_verified", "preferred_currency", "updated_at")
    list_filter = ("phone_verified", "preferred_language")
    search_fields = ("user__email", "phone")
    raw_id_fields = ("user", "preferred_currency", "default_address")


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    """Admin interface for customer addresses."""

    list_display = ("label", "customer_profile", "city", "is_default", "updated_at")
    list_filter = ("is_default", "city")
    search_fields = ("label", "line1", "customer_profile__user__email")
    raw_id_fields = ("customer_profile",)


@admin.register(SavedPaymentMethod)
class SavedPaymentMethodAdmin(admin.ModelAdmin):
    """Admin interface for tokenized payment methods."""

    list_display = ("customer_profile", "card_brand", "last4", "is_default", "updated_at")
    list_filter = ("card_brand", "is_default")
    search_fields = ("customer_profile__user__email", "last4")
    raw_id_fields = ("customer_profile",)


@admin.register(OTPRequest)
class OTPRequestAdmin(admin.ModelAdmin):
    """Admin interface for OTP requests (hash only, never plaintext)."""

    list_display = ("phone", "purpose", "expires_at", "is_used", "attempt_count", "created_at")
    list_filter = ("purpose", "is_used")
    search_fields = ("phone",)
    readonly_fields = ("otp_hash",)


class WishlistItemInline(admin.TabularInline):
    model = WishlistItem
    extra = 0


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ("id", "customer_profile", "session_key", "updated_at")
    inlines = [WishlistItemInline]


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("customer_profile", "product", "status", "quantity", "updated_at")
    list_filter = ("status",)
