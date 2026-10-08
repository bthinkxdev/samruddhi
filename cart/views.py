"""HTTP views for the cart app."""

from __future__ import annotations

import json

from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from cart.exceptions import CartItemNotFoundError, InsufficientStockError
from cart.forms import CartCouponForm, CartQuantityForm
from cart.selectors import get_cart_count, get_cart_for_request, get_cart_summary, get_wishlist_count, get_cart_product_ids
from cart.services import (
    add_to_cart,
    adjust_cart_item_quantity,
    apply_coupon,
    get_or_create_cart,
    remove_coupon,
    remove_cart_item,
    toggle_wishlist,
)
from cart.models import CartItem
from catalog.selectors import get_product_for_cart_add
from core import meta_pixel
from marketing.exceptions import InvalidCouponError


def _line_event(name: str, *, product, variant, quantity: int, price, custom: bool = False) -> dict:
    """Meta Pixel event for one cart / wishlist line."""
    params = meta_pixel.product_params(product, price=price, quantity=quantity, variant=variant)
    return meta_pixel.event(name, params, custom=custom)


def _mpx_trigger(event: dict) -> dict:
    """HX-Trigger fragment that makes meta_pixel.js fire ``event`` in the browser."""
    return {"mpxEvent": event}


def _cart_drawer_response(request: HttpRequest, *, error: str | None = None, error_item_id: int | None = None, hx_triggers: dict | None = None) -> HttpResponse:
    """Render cart drawer partial; optionally attach HTMX trigger headers."""
    cart = get_cart_for_request(request=request)
    summary = get_cart_summary(cart=cart) if cart else None
    from marketing.selectors import has_any_active_coupons
    response = render(
        request,
        "cart/partials/drawer.html",
        {
            "summary": summary,
            "cart_count": summary.item_count if summary else 0,
            "has_active_coupons": has_any_active_coupons(),
            "error": error,
            "error_item_id": error_item_id,
        },
    )
    if hx_triggers:
        response["HX-Trigger"] = json.dumps(hx_triggers)
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    return response


@require_GET
def cart_drawer_view(request: HttpRequest) -> HttpResponse:
    """HTMX partial for the cart drawer."""
    return _cart_drawer_response(request)


def _cart_page_response(
    request: HttpRequest, *, error: str | None = None, error_item_id: int | None = None, hx_triggers: dict | None = None
) -> HttpResponse:
    """Render the standalone cart page's swappable body; optionally attach HTMX triggers."""
    cart = get_cart_for_request(request=request)
    summary = get_cart_summary(cart=cart) if cart else None
    from marketing.selectors import has_any_active_coupons
    response = render(
        request,
        "cart/partials/page_body.html",
        {
            "summary": summary,
            "cart_count": summary.item_count if summary else 0,
            "error": error,
            "error_item_id": error_item_id,
            "has_active_coupons": has_any_active_coupons(),
        },
    )
    if hx_triggers:
        response["HX-Trigger"] = json.dumps(hx_triggers)
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    return response


@require_GET
def cart_page_view(request: HttpRequest) -> HttpResponse:
    """Standalone cart page — full item list, coupon box, and order summary."""
    cart = get_or_create_cart(request=request)
    summary = get_cart_summary(cart=cart)
    from marketing.selectors import has_any_active_coupons
    response = render(
        request,
        "cart/cart_page.html",
        {
            "summary": summary,
            "cart_count": summary.item_count,
            "has_active_coupons": has_any_active_coupons(),
            "mpx_events": (
                [
                    meta_pixel.event(
                        "ViewCart",
                        meta_pixel.lines_params(summary.lines, value=summary.subtotal, currency=cart.currency),
                        custom=True,
                    )
                ]
                if summary.lines
                else []
            ),
        },
    )
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    return response


@require_GET
def cart_count_view(request: HttpRequest) -> HttpResponse:
    """HTMX partial for the header cart badge — lightweight COUNT only."""
    return render(
        request,
        "cart/partials/count_badge.html",
        {"count": get_cart_count(request=request)},
    )


@require_GET
def cart_status_view(request: HttpRequest) -> JsonResponse:
    """JSON endpoint returning active cart count, product IDs, and item keys for JS state sync."""
    cart = get_cart_for_request(request=request)
    cart_item_keys = []
    count = 0
    if cart:
        for pid, vid, qty in CartItem.objects.filter(cart=cart).values_list("product_id", "variant_id", "quantity"):
            cart_item_keys.append(f"{pid}_{vid}" if vid else f"{pid}")
            count += qty
    return JsonResponse({
        "cart_product_ids": list(get_cart_product_ids(cart=cart)),
        "cart_count": count,
        "cart_item_keys": cart_item_keys,
    })


@require_GET
def wishlist_count_view(request: HttpRequest) -> HttpResponse:
    """HTMX partial for wishlist badges — lightweight COUNT only."""
    return render(
        request,
        "cart/partials/wishlist_count_badge.html",
        {"count": get_wishlist_count(request=request)},
    )


@require_POST
def cart_add_view(request: HttpRequest) -> HttpResponse:
    """Add product to persistent cart and return drawer partial or redirect to checkout."""
    product_id = int(request.POST.get("product_id", 0))
    quantity = int(request.POST.get("quantity", 1))
    variant_id_raw = request.POST.get("variant_id")
    variant_id = int(variant_id_raw) if variant_id_raw else None

    product, variant = get_product_for_cart_add(product_id=product_id, variant_id=variant_id)
    if product is None:
        raise Http404("Product not found.")

    buy_now = request.POST.get("buy_now") == "true"
    if buy_now:
        if not request.session.session_key:
            request.session.create()
        session_key = f"bn_{request.session.session_key}"[:40]
        from core.selectors import get_default_currency
        from cart.models import Cart
        cart = Cart.objects.filter(session_key=session_key).first()
        if not cart:
            cart = Cart.objects.create(
                session_key=session_key,
                currency=get_default_currency(),
            )
        else:
            cart.items.all().delete()
            if cart.coupon_code:
                from decimal import Decimal
                cart.coupon_code = ""
                cart.coupon_discount = Decimal("0.00")
                cart.save(update_fields=["coupon_code", "coupon_discount", "updated_at"])
        request.session["checkout_mode"] = "buy_now"
        request.session["buy_now_cart_id"] = cart.pk
    else:
        cart = get_or_create_cart(request=request)
        request.session["checkout_mode"] = "cart"

    try:
        new_item = add_to_cart(
            cart=cart,
            product=product,
            variant=variant,
            quantity=quantity,
            overwrite=True,
        )
    except InsufficientStockError as exc:
        from django.contrib import messages
        messages.error(request, str(exc))
        if request.headers.get("HX-Request") and not buy_now:
            return _cart_drawer_response(request, error=str(exc))
        # If buy_now or not htmx, redirect back to referer
        return redirect(request.META.get("HTTP_REFERER", "/"))

    add_event = _line_event(
        "AddToCart", product=product, variant=variant, quantity=quantity, price=new_item.unit_price_at_add
    )

    if buy_now:
        #the redirect to checkout would discard an HX-Trigger event, so it rides the session
        meta_pixel.queue_event(request, add_event["name"], add_event["params"])
        from django.urls import reverse
        checkout_url = reverse("checkout:checkout")
        if request.headers.get("HX-Request"):
            response = HttpResponse(status=204)
            response["HX-Redirect"] = checkout_url
            return response
        return redirect("checkout:checkout")

    if not request.headers.get("HX-Request"):
        meta_pixel.queue_event(request, add_event["name"], add_event["params"])

    return _cart_drawer_response(
        request,
        hx_triggers={
            "cartItemAdded": {"product_id": product.pk, "variant_id": variant.pk if variant else None},
            **_mpx_trigger(add_event),
        },
    )


def _remove_line(request: HttpRequest) -> dict:
    """Remove the posted cart line; return the HX triggers (incl. the RemoveFromCart event)."""
    cart = get_cart_for_request(request=request)
    removed_product_id = None
    removed_event = None
    if cart:
        cart_item_id = int(request.POST.get("cart_item_id", 0))
        item = CartItem.objects.select_related("product", "variant").filter(
            cart=cart, pk=cart_item_id
        ).first()
        removed_product_id = remove_cart_item(cart=cart, cart_item_id=cart_item_id)
        if item:
            removed_event = _line_event(
                "RemoveFromCart",
                product=item.product,
                variant=item.variant,
                quantity=item.quantity,
                price=item.unit_price_at_add,
                custom=True,
            )

    triggers = {"cartUpdated": None}
    if removed_product_id:
        triggers["cartItemRemoved"] = {"product_id": removed_product_id}
    if removed_event:
        triggers.update(_mpx_trigger(removed_event))
    return triggers


@require_POST
def cart_remove_view(request: HttpRequest) -> HttpResponse:
    """Remove a cart line and return drawer partial."""
    return _cart_drawer_response(request, hx_triggers=_remove_line(request))


@require_POST
def cart_page_remove_view(request: HttpRequest) -> HttpResponse:
    return _cart_page_response(request, hx_triggers=_remove_line(request))


@require_POST
def cart_quantity_view(request: HttpRequest) -> HttpResponse:
    """Increment/decrement a cart line's quantity (+1/-1); deletes at zero."""
    form = CartQuantityForm(request.POST)
    is_drawer = request.POST.get("is_drawer") == "1" or request.headers.get("HX-Target") == "cart-drawer-body"

    if not form.is_valid():
        if is_drawer:
            return _cart_drawer_response(request, hx_triggers={"cartUpdated": None})
        return _cart_page_response(request, error=_("Could not update quantity."))

    cart = get_cart_for_request(request=request)
    if cart is None:
        raise Http404("Cart not found.")

    previous = CartItem.objects.filter(cart=cart, pk=form.cleaned_data["cart_item_id"]).values_list(
        "quantity", flat=True
    ).first()
    try:
        updated_item = adjust_cart_item_quantity(
            cart=cart,
            cart_item_id=form.cleaned_data["cart_item_id"],
            delta=form.cleaned_data["delta"],
        )
    except CartItemNotFoundError:
        if is_drawer:
            return _cart_drawer_response(request, hx_triggers={"cartUpdated": None})
        return _cart_page_response(request, error=_("That item is no longer in your cart."))
    except InsufficientStockError as exc:
        item_id = form.cleaned_data["cart_item_id"] if form.is_valid() else None
        if is_drawer:
            return _cart_drawer_response(request, error=str(exc), error_item_id=item_id)
        return _cart_page_response(request, error=str(exc), error_item_id=item_id)

    triggers = {"cartUpdated": None}
    change = updated_item.quantity - (previous or updated_item.quantity)
    if change:
        triggers.update(
            _mpx_trigger(
                _line_event(
                    "AddToCart" if change > 0 else "RemoveFromCart",
                    product=updated_item.product,
                    variant=updated_item.variant,
                    quantity=abs(change),
                    price=updated_item.unit_price_at_add,
                    custom=change < 0,
                )
            )
        )
    if is_drawer:
        return _cart_drawer_response(request, hx_triggers=triggers)
    return _cart_page_response(request, hx_triggers=triggers)


@require_POST
def cart_coupon_apply_view(request: HttpRequest) -> HttpResponse:
    """Validate and apply a coupon code to the cart."""
    form = CartCouponForm(request.POST)
    if not form.is_valid():
        return _cart_page_response(request, error=_("Enter a coupon code."))

    cart = get_cart_for_request(request=request)
    if cart is None:
        raise Http404("Cart not found.")

    try:
        apply_coupon(cart=cart, code=form.cleaned_data["code"])
    except InvalidCouponError as exc:
        return _cart_page_response(request, error=str(exc))

    return _cart_page_response(request, hx_triggers={"cartUpdated": None})


@require_POST
def cart_coupon_remove_view(request: HttpRequest) -> HttpResponse:
    """Remove any applied coupon from the cart."""
    cart = get_cart_for_request(request=request)
    if cart:
        remove_coupon(cart=cart)
    return _cart_page_response(request, hx_triggers={"cartUpdated": None})


@require_POST
def wishlist_toggle_view(request: HttpRequest) -> HttpResponse:
    """Toggle wishlist item; return JSON for HTMX or redirect back."""
    product_id = int(request.POST.get("product_id", 0))
    added = toggle_wishlist(request=request, product_id=product_id)
    count = get_wishlist_count(request=request)
    wishlist_product, _variant = get_product_for_cart_add(product_id=product_id, variant_id=None)
    wishlist_event = (
        _line_event(
            "AddToWishlist" if added else "RemoveFromWishlist",
            product=wishlist_product,
            variant=None,
            quantity=1,
            price=getattr(wishlist_product, "effective_base_price", wishlist_product.base_price),
            custom=not added,
        )
        if wishlist_product
        else None
    )
    if request.headers.get("HX-Request"):
        response = HttpResponse(
            json.dumps(
                {
                    "status": "added" if added else "removed",
                    "product_id": product_id,
                    "added": added,
                    "count": count,
                }
            ),
            content_type="application/json",
        )
        response["HX-Trigger"] = json.dumps(
            {
                "wishlistUpdated": {
                    "added": added,
                    "product_id": product_id,
                    "count": count,
                },
                **(_mpx_trigger(wishlist_event) if wishlist_event else {}),
            }
        )
        return response
    if wishlist_event:
        meta_pixel.queue_event(
            request, wishlist_event["name"], wishlist_event["params"], custom=wishlist_event["custom"]
        )
    return redirect(request.META.get("HTTP_REFERER", "/"))
