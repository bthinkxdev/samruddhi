"""Django admin registrations for the marketing app."""

from __future__ import annotations

from django.contrib import admin

from marketing.models import (
    AbandonedCartRecovery,
    Coupon,
    CouponRedemption,
    FlashSale,
    NewsletterSubscriber,
    Referral,
)


class CouponRedemptionInline(admin.TabularInline):
    model = CouponRedemption
    extra = 0
    readonly_fields = ("customer_profile", "order", "created_at")


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "discount_type",
        "discount_value",
        "min_order_value",
        "max_uses",
        "valid_until",
        "is_active",
    )
    list_filter = ("discount_type", "is_active")
    search_fields = ("code",)
    filter_horizontal = ("applicable_collections",)
    inlines = [CouponRedemptionInline]





@admin.register(FlashSale)
class FlashSaleAdmin(admin.ModelAdmin):
    list_display = ("name", "discount_percentage", "starts_at", "ends_at", "is_active")
    list_filter = ("is_active",)
    filter_horizontal = ("products",)


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ("code", "referrer", "referred_email", "is_converted")


@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "is_active", "unsubscribed_at", "created_at")
    list_filter = ("is_active",)
    search_fields = ("email",)


@admin.register(AbandonedCartRecovery)
class AbandonedCartRecoveryAdmin(admin.ModelAdmin):
    list_display = ("cart", "notified_at", "created_at")
    list_filter = ("notified_at",)
    readonly_fields = ("cart", "notified_at", "created_at")
