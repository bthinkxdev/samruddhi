"""HTTP views for the orders app."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from orders.selectors import get_order_tracking_view, get_customer_orders


@login_required
@require_GET
def order_tracking_view(request: HttpRequest, order_id: int) -> HttpResponse:
    """Customer order tracking page with status timeline."""
    profile = request.user.customer_profile
    tracking = get_order_tracking_view(order_id=order_id, customer_profile=profile)
    if tracking is None:
        raise Http404("Order not found.")
    return render(
        request,
        "orders/tracking.html",
        {
            "tracking": tracking,
            "order": tracking.order,
            "status_history": tracking.status_history,
        },
    )


@login_required
@require_GET
def order_list_view(request: HttpRequest) -> HttpResponse:
    """Customer order history page."""
    profile = request.user.customer_profile
    page = int(request.GET.get("page", 1))
    orders_page = get_customer_orders(customer_profile=profile, page=page, page_size=20)
    
    return render(
        request,
        "orders/order_list.html",
        {
            "orders": orders_page["results"],
            "pagination": {
                "page": orders_page["page"],
                "total_count": orders_page["total_count"],
                "total_pages": orders_page["total_pages"],
                "has_next": orders_page["has_next"],
                "has_previous": orders_page["has_previous"],
            }
        },
    )


@login_required
@require_GET
def order_detail_view(request: HttpRequest, order_id: int) -> HttpResponse:
    """Customer order details page."""
    profile = request.user.customer_profile
    tracking = get_order_tracking_view(order_id=order_id, customer_profile=profile)
    if tracking is None:
        raise Http404("Order not found.")
    
    return render(
        request,
        "orders/order_detail.html",
        {
            "order": tracking.order,
            "items": tracking.order.items.all(),
            "tracking": tracking,
        },
    )
