"""Write operations and business rules for the marketing app."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from marketing.exceptions import InvalidCouponError
from marketing.models import (
    Coupon,
    CouponDiscountType,
    CouponRedemption,
    NewsletterSubscriber,
)


def validate_coupon_for_cart(
    *,
    code: str,
    cart_subtotal: Decimal,
    customer_profile_id: Optional[int] = None,
    cart_collection_ids: Optional[list[int]] = None,
) -> dict[str, Decimal | str]:
    """
    Validate a coupon and return the discount amount for a cart subtotal.

    Enforces date windows, usage limits, min order value, and collection scope.
    """
    now = timezone.now()
    coupon = (
        Coupon.objects.filter(code__iexact=code.strip(), is_active=True)
        .annotate(redemption_count=Count("redemptions"))
        .first()
    )
    if coupon is None:
        raise InvalidCouponError("Invalid or expired coupon code.")

    if coupon.valid_from and now < coupon.valid_from:
        raise InvalidCouponError("Coupon is not yet valid.")
    if coupon.valid_until and now > coupon.valid_until:
        raise InvalidCouponError("Coupon has expired.")

    if cart_subtotal < coupon.min_order_value:
        raise InvalidCouponError("Order does not meet the minimum value for this coupon.")

    if coupon.max_uses is not None and coupon.redemption_count >= coupon.max_uses:
        raise InvalidCouponError("Coupon usage limit reached.")

    if customer_profile_id and coupon.max_uses_per_customer is not None:
        customer_uses = CouponRedemption.objects.filter(
            coupon=coupon,
            customer_profile_id=customer_profile_id,
        ).count()
        if customer_uses >= coupon.max_uses_per_customer:
            raise InvalidCouponError(
                "You have already used this coupon the maximum number of times."
            )

    if cart_collection_ids is not None and coupon.applicable_collections.exists():
        allowed = set(coupon.applicable_collections.values_list("pk", flat=True))
        if not allowed.intersection(cart_collection_ids):
            raise InvalidCouponError("Coupon does not apply to items in your cart.")

    discount_type = coupon.discount_type
    if discount_type in (CouponDiscountType.PERCENTAGE, "percent", "percentage"):
        discount = (cart_subtotal * coupon.discount_value / Decimal("100")).quantize(
            Decimal("0.01")
        )
    else:
        discount = min(coupon.discount_value, cart_subtotal)

    return {"code": coupon.code, "discount_amount": discount, "coupon_id": coupon.pk}


@transaction.atomic
def record_coupon_redemption(
    *,
    coupon_id: int,
    customer_profile_id: int,
    order_id: Optional[int] = None,
) -> CouponRedemption:
    """Record a coupon redemption after successful order placement."""
    return CouponRedemption.objects.create(
        coupon_id=coupon_id,
        customer_profile_id=customer_profile_id,
        order_id=order_id,
    )


@transaction.atomic
def subscribe_newsletter(*, email: str) -> tuple[NewsletterSubscriber, bool]:
    """Subscribe an email to the newsletter."""
    subscriber, created = NewsletterSubscriber.objects.get_or_create(
        email=email.strip().lower(),
        defaults={"is_active": True, "unsubscribed_at": None},
    )
    is_new = created
    if not created and not subscriber.is_active:
        subscriber.is_active = True
        subscriber.unsubscribed_at = None
        subscriber.save(update_fields=["is_active", "unsubscribed_at", "updated_at"])
        is_new = True
    return subscriber, is_new


@transaction.atomic
def unsubscribe_newsletter(*, email: str) -> None:
    """Unsubscribe an email from the newsletter."""
    NewsletterSubscriber.objects.filter(email=email.strip().lower()).update(
        is_active=False,
        unsubscribed_at=timezone.now(),
    )
