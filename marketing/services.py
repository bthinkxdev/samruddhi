"""Write operations and business rules for the marketing app."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from marketing.exceptions import InvalidCouponError
from marketing.models import (
    Coupon,
    CouponDiscountType,
    CouponRedemption,
    NewsletterSubscriber,
)


#an online order that never gets paid stops holding a coupon use after this long
PENDING_REDEMPTION_HOLD = timedelta(minutes=30)


def _live_redemptions(*, coupon: Coupon, cart_id: Optional[int] = None):
    """
    Redemptions that still count against the coupon's limits.

    Cancelled/refunded orders and stale unpaid online orders release their use.
    The caller's own cart is excluded so retrying payment on a pending order
    doesn't invalidate the coupon that order already holds.
    """
    from orders.models import OrderStatus

    cutoff = timezone.now() - PENDING_REDEMPTION_HOLD
    qs = coupon.redemptions.exclude(
        Q(order__order_status__in=[OrderStatus.CANCELLED, OrderStatus.REFUNDED])
        | Q(order__order_status=OrderStatus.CHECKOUT_PENDING, order__created_at__lt=cutoff)
    )
    if cart_id:
        qs = qs.exclude(order__cart_id=cart_id)
    return qs


def _check_usage_limits(
    *, coupon: Coupon, customer_profile_id: Optional[int], cart_id: Optional[int]
) -> None:
    live = _live_redemptions(coupon=coupon, cart_id=cart_id)
    if coupon.max_uses is not None and live.count() >= coupon.max_uses:
        raise InvalidCouponError("Coupon usage limit reached.")
    if customer_profile_id and coupon.max_uses_per_customer is not None:
        if live.filter(customer_profile_id=customer_profile_id).count() >= coupon.max_uses_per_customer:
            raise InvalidCouponError(
                "You have already used this coupon the maximum number of times."
            )


def validate_coupon_for_cart(
    *,
    code: str,
    cart_subtotal: Decimal,
    cart_lines: list[tuple[Decimal, set[int]]],
    customer_profile_id: Optional[int] = None,
    cart_id: Optional[int] = None,
) -> dict[str, Decimal | str]:
    """
    Validate a coupon and return the discount amount for a cart.

    ``cart_lines`` is ``(line_subtotal, collection_ids)`` per cart line. Enforces
    date windows, usage limits, min order value (on the whole cart) and collection
    scope — a collection-scoped coupon discounts only its eligible lines.
    """
    now = timezone.now()
    coupon = Coupon.objects.filter(code__iexact=code.strip(), is_active=True).first()
    if coupon is None:
        raise InvalidCouponError("Invalid or expired coupon code.")

    if coupon.valid_from and now < coupon.valid_from:
        raise InvalidCouponError("Coupon is not yet valid.")
    if coupon.valid_until and now > coupon.valid_until:
        raise InvalidCouponError("Coupon has expired.")

    if cart_subtotal < coupon.min_order_value:
        raise InvalidCouponError("Order does not meet the minimum value for this coupon.")

    _check_usage_limits(coupon=coupon, customer_profile_id=customer_profile_id, cart_id=cart_id)

    eligible_subtotal = cart_subtotal
    allowed = set(coupon.applicable_collections.values_list("pk", flat=True))
    if allowed:
        eligible_subtotal = sum(
            (amount for amount, collection_ids in cart_lines if allowed & collection_ids),
            Decimal("0.00"),
        )
        if eligible_subtotal <= 0:
            raise InvalidCouponError("Coupon does not apply to items in your cart.")

    if coupon.discount_type == CouponDiscountType.PERCENTAGE:
        discount = (eligible_subtotal * coupon.discount_value / Decimal("100")).quantize(
            Decimal("0.01")
        )
    else:
        discount = coupon.discount_value
    discount = min(discount, eligible_subtotal)

    return {"code": coupon.code, "discount_amount": discount, "coupon_id": coupon.pk}


@transaction.atomic
def record_coupon_redemption(
    *,
    code: str,
    customer_profile_id: Optional[int],
    order_id: int,
    cart_id: int,
) -> CouponRedemption:
    """
    Record a coupon redemption when an order is created.

    Locks the coupon row and re-checks the usage limits so concurrent checkouts
    can't both take the last remaining use. Raises InvalidCouponError if the
    limit was reached in the meantime (the caller's transaction rolls back).
    """
    coupon = Coupon.objects.select_for_update().filter(code__iexact=code.strip()).first()
    if coupon is None or not coupon.is_currently_active:
        raise InvalidCouponError("Invalid or expired coupon code.")
    _check_usage_limits(coupon=coupon, customer_profile_id=customer_profile_id, cart_id=cart_id)
    return CouponRedemption.objects.create(
        coupon=coupon,
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
