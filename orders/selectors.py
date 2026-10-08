"""Read-only query functions for the orders app; views must not call the ORM directly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from django.core.paginator import Paginator
from django.db.models import F, Prefetch

from accounts.models import CustomerProfile
from orders.models import Order, OrderItem, OrderStatusHistory


@dataclass(frozen=True)
class OrderTrackingView:
    """Hydrated order data for the customer tracking timeline."""

    order: Order
    status_history: list[OrderStatusHistory]


def get_customer_orders(
    *,
    customer_profile: CustomerProfile,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """
    Return a paginated page of orders for a customer dashboard.

    Query guarantee: 2 queries — COUNT + page SELECT with select_related.
    """
    queryset = (
        Order.objects.select_related(
            "currency",
        )
        .filter(customer_profile=customer_profile)
        .order_by(F("success_at").desc(nulls_last=True), "-created_at")
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


def get_recent_orders_for_customer(*, customer_profile_id: int, limit: int = 5) -> list[Order]:
    """
    Return the most recent orders for a customer profile.

    Delegates to ``get_customer_orders`` page 1 and slices to ``limit``.
    Query guarantee: 2 queries (COUNT + page SELECT).
    """
    profile = CustomerProfile.objects.filter(pk=customer_profile_id).first()
    if profile is None:
        return []
    page = get_customer_orders(customer_profile=profile, page=1, page_size=limit)
    return page["results"]


def get_order_tracking_view(
    *,
    order_id: int,
    customer_profile: Optional[CustomerProfile] = None,
) -> Optional[OrderTrackingView]:
    """
    Return order tracking data with status history in one efficient call.

    Query guarantee: 1 SELECT on order with select_related + 1 prefetch for history.
    """
    queryset = Order.objects.select_related(
        "customer_profile",
        "currency",
        "proof_of_delivery",
    ).prefetch_related(
        Prefetch(
            "status_history",
            queryset=OrderStatusHistory.objects.select_related("changed_by").order_by("changed_at"),
        ),
        Prefetch(
            "items",
            queryset=OrderItem.objects.select_related(
                "product",
                "variant",
            ),
        ),
    )
    if customer_profile is not None:
        queryset = queryset.filter(customer_profile=customer_profile)

    order = queryset.filter(pk=order_id).first()
    if order is None:
        return None

    history = list(order.status_history.all())
    return OrderTrackingView(order=order, status_history=history)
