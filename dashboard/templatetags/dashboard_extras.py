"""Template helpers for the admin dashboard."""

from __future__ import annotations

from django import template
from django.urls import reverse

register = template.Library()


@register.simple_tag
def cell_value(obj, column):
    """Resolve a column's value from an object, supporting dotted paths + callables."""
    name = column.get("name")
    if not name:
        return ""
    value = obj
    for part in name.split("."):
        if value is None:
            return ""
        value = getattr(value, part, None)
        if callable(value):
            value = value()
    return value


@register.simple_tag
def row_action_url(basename, action, pk):
    """Build a dashboard CRUD url like dashboard:product-update for a given pk."""
    return reverse(f"dashboard:{basename}-{action}", args=[pk])


@register.filter
def get_item(dictionary, key):
    """Look up a dict value by variable key inside templates."""
    if hasattr(dictionary, "get"):
        return dictionary.get(key)
    return None


_STATUS_PILL = {
    "checkout_pending": "pill-amber",
    "placed_cod": "pill-amber",
    "confirmed": "pill-blue",
    "ready_to_ship": "pill-blue",
    "picked_up": "pill-blue",
    "in_transit": "pill-blue",
    "out_for_delivery": "pill-blue",
    "delivered": "pill-green",
    "cancelled": "pill-red",
    "refunded": "pill-red",
    "success": "pill-green",
    "pending": "pill-amber",
    "failed": "pill-red",
    "approved": "pill-green",
    "rejected": "pill-red",
}


@register.filter
def status_pill(value):
    """Return the soft-pill CSS class for an order/payment/approval status code."""
    return _STATUS_PILL.get(str(value).lower(), "pill-gray")


_ORDER_STATUS_BADGE = {
    "checkout_pending": "bg-warning-subtle text-warning",
    "placed_cod": "bg-warning-subtle text-warning",
    "confirmed": "bg-success-subtle text-success",
    "ready_to_ship": "bg-primary-subtle text-primary",
    "picked_up": "bg-info-subtle text-info",
    "in_transit": "bg-info-subtle text-info",
    "out_for_delivery": "bg-info-subtle text-info",
    "delivered": "bg-success-subtle text-success",
    "cancelled": "bg-danger-subtle text-danger",
    "refunded": "bg-secondary-subtle text-secondary",
}


@register.filter
def order_status_badge(value):
    """Return the Bootstrap 'bg-X-subtle text-X' class pair for an order status code."""
    return _ORDER_STATUS_BADGE.get(str(value).lower(), "bg-secondary-subtle text-secondary")


@register.filter
def primary_image(product):
    """Return the URL of a product's primary (or first) image, else empty string."""
    try:
        images = list(product.images.all())
    except (AttributeError, ValueError):
        return ""
    if not images:
        return ""
    chosen = next((im for im in images if im.is_primary), images[0])
    try:
        return chosen.image.url if chosen.image else ""
    except ValueError:
        return ""
