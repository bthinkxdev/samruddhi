"""Template context processors for storefront chrome."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from core import meta_pixel
from cart.selectors import (
    get_cart_count,
    get_cart_item_keys,
    get_cart_product_ids,
    get_wishlist_count,
    get_wishlist_product_ids,
)
from catalog.selectors import get_collection_tree
from core.selectors import get_currency_by_code, get_default_currency
from core.services import get_site_settings


def storefront(request: HttpRequest) -> dict[str, Any]:
    """Inject navigation, cart, and locale data into every template."""
    if request.method == "GET":
        path = request.path_info
        is_checkout_or_payment = (
            path.startswith("/checkout/")
            or path.startswith("/payments/")
            or path.startswith("/admin/")
            or path.startswith("/static/")
            or path.startswith("/media/")
            or path.startswith("/__debug__/")
            or path == "/favicon.ico"
            or path.startswith("/cart/count/")
            or path.startswith("/cart/drawer/")
            or path.startswith("/cart/wishlist/count/")
        )
        if not is_checkout_or_payment:
            pass


    default_currency = get_default_currency()
    session_currency = request.session.get("storefront_currency", "")
    display_currency = (
        get_currency_by_code(code=session_currency) if session_currency else default_currency
    )
    wishlist_product_ids = get_wishlist_product_ids(request=request)
    
    from cms.models import AnnouncementBarItem, BlogPost, Page

    site_settings = get_site_settings()

    return {
        "meta_pixel_id": meta_pixel.pixel_id(site_settings),
        "site_settings": site_settings,
        "collection_tree": get_collection_tree(),
        "announcement_items": AnnouncementBarItem.objects.filter(is_active=True).order_by("display_order"),
        "has_blog_posts": BlogPost.objects.filter(BlogPost.live_q()).exists(),
        "cart_count": get_cart_count(request=request),
        "cart_product_ids": get_cart_product_ids(request=request),
        "cart_item_keys": get_cart_item_keys(request=request),
        "wishlist_count": get_wishlist_count(request=request),
        "wishlist_product_ids": wishlist_product_ids,
        "default_currency": default_currency,
        "display_currency": display_currency,
        "session_language": request.session.get("django_language", ""),
        "session_currency": session_currency,

        "shell_only": request.META.get("HTTP_X_SHELL_RERENDER") == "true",
        "cms_pages": Page.objects.filter(Page.live_q()),
    }
