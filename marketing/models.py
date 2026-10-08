"""Data layer for the marketing app — models only, no business logic."""

from __future__ import annotations

from django.db import models

from core.models import TimeStampedModel


class CouponDiscountType(models.TextChoices):
    """How a coupon discount is calculated."""

    PERCENTAGE = "percent", "Percentage"
    FIXED = "fixed", "Fixed amount"


class Coupon(TimeStampedModel):
    """Promotional coupon with usage limits and collection scoping."""

    code = models.CharField(max_length=40, unique=True, db_index=True, verbose_name="Code")
    discount_type = models.CharField(
        max_length=20,
        choices=CouponDiscountType.choices,
        default=CouponDiscountType.PERCENTAGE,
    )
    discount_value = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Value")
    min_order_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Minimum order value",
    )
    max_uses = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Max total uses",
        help_text="Blank = unlimited.",
    )
    max_uses_per_customer = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Max uses per customer",
    )
    valid_from = models.DateTimeField(null=True, blank=True, db_index=True)
    valid_until = models.DateTimeField(null=True, blank=True, db_index=True)
    applicable_collections = models.ManyToManyField(
        "catalog.Collection",
        blank=True,
        related_name="coupons",
        verbose_name="Applicable collections",
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = "Coupon"
        verbose_name_plural = "Coupons"
        indexes = [
            models.Index(fields=["is_active", "code"], name="mkt_coupon_active_code_idx"),
        ]

    @property
    def is_currently_active(self) -> bool:
        from django.utils import timezone
        if not self.is_active:
            return False
        now = timezone.now()
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        return True

    def __str__(self) -> str:
        return self.code


class CouponRedemption(TimeStampedModel):
    """Tracks coupon usage per customer."""

    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name="redemptions")
    customer_profile = models.ForeignKey(
        "accounts.CustomerProfile",
        on_delete=models.CASCADE,
        related_name="coupon_redemptions",
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coupon_redemptions",
    )

    class Meta:
        verbose_name = "Coupon redemption"
        verbose_name_plural = "Coupon redemptions"
        indexes = [
            models.Index(fields=["coupon", "customer_profile"], name="mkt_coupon_redemption_idx"),
        ]

class FlashSale(TimeStampedModel):
    """Time-boxed percentage discount on selected products."""

    name = models.CharField(max_length=120)
    products = models.ManyToManyField("catalog.Product", related_name="flash_sales")
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    starts_at = models.DateTimeField(db_index=True)
    ends_at = models.DateTimeField(db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = "Flash sale"
        verbose_name_plural = "Flash sales"

    @property
    def is_currently_active(self) -> bool:
        from django.utils import timezone
        if not self.is_active:
            return False
        now = timezone.now()
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True

    def __str__(self) -> str:
        return self.name


class AbandonedCartRecovery(TimeStampedModel):
    """Tracks recovery notifications sent for abandoned carts."""

    cart = models.ForeignKey("cart.Cart", on_delete=models.CASCADE, related_name="recovery_logs")
    notified_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Abandoned cart recovery"
        verbose_name_plural = "Abandoned cart recoveries"
        indexes = [
            models.Index(fields=["cart"], name="mkt_abandoned_cart_idx"),
        ]


class Referral(TimeStampedModel):
    """Customer referral code tracking."""

    referrer = models.ForeignKey(
        "accounts.CustomerProfile",
        on_delete=models.CASCADE,
        related_name="referrals_made",
    )
    referred_email = models.EmailField(db_index=True)
    code = models.CharField(max_length=40, unique=True, db_index=True)
    is_converted = models.BooleanField(default=False, db_index=True)

    class Meta:
        verbose_name = "Referral"
        verbose_name_plural = "Referrals"


class NewsletterSubscriber(TimeStampedModel):
    """Newsletter email subscription."""

    email = models.EmailField(unique=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Newsletter subscriber"
        verbose_name_plural = "Newsletter subscribers"

    def __str__(self) -> str:
        return self.email
