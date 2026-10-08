"""Subscription, wishlist, and gift-reminder services."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from django.contrib.auth.models import User
from django.core import signing
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from accounts.models import (
    CustomerProfile,
    Subscription,
    SubscriptionStatus,
    Wishlist,
    WishlistItem,
)

from cart.models import Cart, CartItem
from catalog.selectors import get_variant_price
from checkout.services import create_checkout_session, place_order, update_checkout_session
from core.selectors import get_default_currency
from recurring.models import RecurrenceStatus, RecurringSchedule

WISHLIST_SHARE_SALT = "accounts.wishlist-share"


@transaction.atomic
def create_subscription(
    *,
    customer_profile: CustomerProfile,
    product_id: int,
    delivery_address_id: int,
    frequency: str,
    next_run_date: date,
    quantity: int = 1,
    created_by: Optional[User] = None,
) -> Subscription:
    """Create a subscription with a linked recurring schedule."""
    subscription = Subscription.objects.create(
        customer_profile=customer_profile,
        product_id=product_id,
        delivery_address_id=delivery_address_id,
        quantity=quantity,
        status=SubscriptionStatus.ACTIVE,
    )
    schedule = RecurringSchedule.objects.create(
        content_object=subscription,
        frequency=frequency,
        next_run_date=next_run_date,
        status=RecurrenceStatus.ACTIVE,
        created_by=created_by,
    )
    subscription.recurring_schedule = schedule
    subscription.save(update_fields=["recurring_schedule", "updated_at"])
    return subscription


@transaction.atomic
def pause_subscription(*, subscription: Subscription) -> Subscription:
    """Pause a subscription by updating the underlying recurring schedule."""
    subscription.status = SubscriptionStatus.PAUSED
    subscription.save(update_fields=["status", "updated_at"])
    if subscription.recurring_schedule_id:
        schedule = subscription.recurring_schedule
        schedule.status = RecurrenceStatus.PAUSED
        schedule.save(update_fields=["status", "updated_at"])
    return subscription


@transaction.atomic
def resume_subscription(*, subscription: Subscription) -> Subscription:
    """Resume a paused subscription."""
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.save(update_fields=["status", "updated_at"])
    if subscription.recurring_schedule_id:
        schedule = subscription.recurring_schedule
        schedule.status = RecurrenceStatus.ACTIVE
        schedule.save(update_fields=["status", "updated_at"])
    return subscription


@transaction.atomic
def cancel_subscription(*, subscription: Subscription) -> Subscription:
    """Cancel a subscription and its recurring schedule."""
    subscription.status = SubscriptionStatus.CANCELLED
    subscription.save(update_fields=["status", "updated_at"])
    if subscription.recurring_schedule_id:
        schedule = subscription.recurring_schedule
        schedule.status = RecurrenceStatus.CANCELLED
        schedule.save(update_fields=["status", "updated_at"])
    return subscription


@transaction.atomic
def execute_subscription_recurrence(*, schedule: RecurringSchedule) -> object:
    """Recurrence handler for customer subscriptions."""
    subscription = schedule.content_object
    if not isinstance(subscription, Subscription):
        raise ValueError("Schedule does not point to a subscription.")
    if subscription.status != SubscriptionStatus.ACTIVE:
        return None

    profile = subscription.customer_profile
    currency = get_default_currency()
    price_data = get_variant_price(product_id=subscription.product_id, variant_id=None)
    cart = Cart.objects.create(customer_profile=profile, currency=currency)
    CartItem.objects.create(
        cart=cart,
        product=subscription.product,
        quantity=subscription.quantity,
        unit_price_at_add=Decimal(price_data["price"]),
    )
    session = create_checkout_session(cart=cart, customer_profile=profile)
    update_checkout_session(checkout_session=session, address=subscription.delivery_address)
    idempotency_key = f"recurring-sub-{schedule.pk}-{schedule.next_run_date}"
    return place_order(
        checkout_session_id=session.pk,
        idempotency_key=idempotency_key,
        gateway_key="card",
        customer_profile=profile,
    )


@transaction.atomic
def get_or_create_wishlist(*, request: HttpRequest) -> Wishlist:
    """Return the persistent wishlist for the current user or guest session."""
    if not request.session.session_key:
        request.session.create()

    if request.user.is_authenticated and hasattr(request.user, "customer_profile"):
        wishlist, _ = Wishlist.objects.get_or_create(
            customer_profile=request.user.customer_profile,
        )
        return wishlist

    return Wishlist.objects.get_or_create(session_key=request.session.session_key)[0]


@transaction.atomic
def add_to_wishlist(*, wishlist: Wishlist, product_id: int) -> WishlistItem:
    """Add a product to a wishlist."""
    item, _ = WishlistItem.objects.get_or_create(wishlist=wishlist, product_id=product_id)
    return item


@transaction.atomic
def remove_from_wishlist(*, wishlist: Wishlist, product_id: int) -> None:
    """Remove a product from a wishlist."""
    WishlistItem.objects.filter(wishlist=wishlist, product_id=product_id).delete()


def generate_wishlist_share_token(*, wishlist: Wishlist) -> str:
    """Create a signed share token for read-only wishlist access."""
    token = signing.dumps({"wishlist_id": wishlist.pk}, salt=WISHLIST_SHARE_SALT)
    wishlist.share_token = token
    wishlist.save(update_fields=["share_token", "updated_at"])
    return token



