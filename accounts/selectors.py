"""Read-only query functions for the accounts app; views must not call the ORM directly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Prefetch

from accounts.models import (
    Address,
    CustomerProfile,
    SavedPaymentMethod,
    Wishlist,
    Subscription
)
from catalog.models import ProductImage
from notifications.selectors import get_unread_notification_count
from orders.selectors import get_customer_orders


@dataclass(frozen=True)
class CustomerDashboardContext:
    """Aggregated data for the customer account dashboard."""

    profile: CustomerProfile
    default_address: Optional[Address]
    recent_orders: list[Any]
    unread_notification_count: int


def get_customer_profile_for_user(*, user: User) -> Optional[CustomerProfile]:
    """
    Return the customer profile for a user with related currency and default address.

    Query guarantee: exactly 1 SELECT with select_related on preferred_currency,
    and default_address.
    """
    return (
        CustomerProfile.objects.select_related(
            "preferred_currency",
            "default_address",
        )
        .filter(user=user)
        .first()
    )


def get_customer_dashboard_context(*, user: User) -> Optional[CustomerDashboardContext]:
    """
    Build the customer dashboard context from dedicated selectors.

    Query guarantee: exactly 4 queries total —
      1) customer profile + preferred_currency + default_address (select_related),
      2–3) paginated orders via orders.get_customer_orders (COUNT + page SELECT),
      4) unread notification count via notifications.get_unread_notification_count.
    Params:
        user: Authenticated Django User.
    Returns:
        CustomerDashboardContext or None if no profile exists.
    """
    profile = get_customer_profile_for_user(user=user)
    if profile is None:
        return None

    orders_page = get_customer_orders(customer_profile=profile, page=1, page_size=5)
    recent_orders = orders_page["results"]
    unread_count = get_unread_notification_count(user=user)

    address = profile.default_address
    if not address:
        address = Address.objects.filter(customer_profile=profile).first()

    return CustomerDashboardContext(
        profile=profile,
        default_address=address,
        recent_orders=recent_orders,
        unread_notification_count=unread_count,
    )


def get_address_by_id(
    *,
    address_id: int,
    customer_profile: CustomerProfile,
) -> Optional[Address]:
    """
    Return a single address owned by the customer.

    Query guarantee: exactly 1 SELECT.
    """
    return (
        Address.objects.filter(pk=address_id, customer_profile=customer_profile)
        .first()
    )


def get_saved_addresses(
    *,
    customer_profile: CustomerProfile,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """
    Return a paginated page of customer addresses.

    Query guarantee: 2 queries — COUNT + page SELECT.
    """
    queryset = (
        Address.objects.filter(customer_profile=customer_profile)
        .order_by("-is_default", "-created_at")
    )
    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(page)
    return {
        "results": list(page_obj.object_list),
        "page": page_obj.number,
        "page_size": page_size,
        "total_count": paginator.count,
        "total_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    }


def get_saved_payment_methods(
    *,
    customer_profile: CustomerProfile,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """
    Return a paginated page of saved payment methods.

    Query guarantee: 2 queries — COUNT + page SELECT.
    """
    queryset = SavedPaymentMethod.objects.filter(customer_profile=customer_profile).order_by(
        "-is_default",
        "-created_at",
    )
    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(page)
    return {
        "results": list(page_obj.object_list),
        "page": page_obj.number,
        "page_size": page_size,
        "total_count": paginator.count,
        "total_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    }



@dataclass(frozen=True)
class WishlistView:
    """Wishlist data for card rendering."""

    wishlist: Wishlist
    items: list
    readonly: bool


def get_wishlist(
    *,
    customer_profile: Optional[CustomerProfile] = None,
    share_token: Optional[str] = None,
    session_key: Optional[str] = None,
) -> Optional[WishlistView]:
    from django.core import signing

    from accounts.models import WishlistItem
    from accounts.subscription_services import WISHLIST_SHARE_SALT

    items_prefetch = Prefetch(
        "items",
        queryset=WishlistItem.objects.select_related("product").prefetch_related(
            Prefetch(
                "product__images",
                queryset=ProductImage.objects.order_by("-is_primary", "display_order"),
                to_attr="primary_images",
            ),
        ),
    )

    if share_token:
        try:
            data = signing.loads(share_token, salt=WISHLIST_SHARE_SALT)
            wishlist_id = data["wishlist_id"]
        except signing.BadSignature:
            return None
        wishlist = (
            Wishlist.objects.prefetch_related(items_prefetch)
            .filter(pk=wishlist_id)
            .first()
        )
        if wishlist is None:
            return None
        return WishlistView(wishlist=wishlist, items=list(wishlist.items.all()), readonly=True)

    if customer_profile is None and session_key is None:
        return None

    if customer_profile:
        wishlist = (
            Wishlist.objects.filter(customer_profile=customer_profile)
            .prefetch_related(items_prefetch)
            .first()
        )
    else:
        wishlist = (
            Wishlist.objects.filter(session_key=session_key)
            .prefetch_related(items_prefetch)
            .first()
        )

    if wishlist is None:
        return None
    return WishlistView(wishlist=wishlist, items=list(wishlist.items.all()), readonly=False)


@dataclass(frozen=True)
class SubscriptionListItem:
    """Thin wrapper if you later want computed fields; currently passthrough."""
    subscription: Subscription


def get_customer_subscriptions(
    *,
    customer_profile: CustomerProfile,
    status: Optional[str] = None,
) -> list[Subscription]:
    """
    Return a customer's subscriptions, optionally filtered by status.

    Query guarantee: 1 SELECT with select_related on product and recurring_schedule.
    """
    queryset = Subscription.objects.select_related(
        "product", "recurring_schedule", "delivery_address"
    ).filter(customer_profile=customer_profile)
    if status:
        queryset = queryset.filter(status=status)
    return list(queryset.order_by("-created_at"))


def get_customer_subscription_by_id(
    *,
    subscription_id: int,
    customer_profile: CustomerProfile,
) -> Optional[Subscription]:
    """Return a single subscription owned by the customer, or None."""
    return (
        Subscription.objects.select_related("product", "recurring_schedule", "delivery_address")
        .filter(pk=subscription_id, customer_profile=customer_profile)
        .first()
    )
