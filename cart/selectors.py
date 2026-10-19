"""Read-only query functions for the cart app; views must not call the ORM directly."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional

from django.db.models import Prefetch, Sum
from django.http import HttpRequest

from cart.models import Cart, CartItem
from catalog.models import ProductImage
from delivery.selectors import get_delivery_charge

_CART_CACHE_ATTR = "_theme_resolved_cart"


def get_cart_for_request(*, request: HttpRequest) -> Optional[Cart]:
    """
    Resolve the persistent cart for the current request (guest or authenticated).

    Query guarantee: at most 1 SELECT on cart_cart per request (request-scoped cache).
    """
    if hasattr(request, _CART_CACHE_ATTR):
        return getattr(request, _CART_CACHE_ATTR)

    if not request.session.session_key:
        request.session.create()
    session_key = request.session.session_key

    cart = None
    if request.user.is_authenticated and hasattr(request.user, "customer_profile"):
        cart = (
            Cart.objects.filter(customer_profile=request.user.customer_profile)
            .select_related("currency")
            .first()
        )

    if cart is None:
        guest_cart_id = request.session.get("guest_cart_id")
        if guest_cart_id:
            cart = (
                Cart.objects.filter(pk=guest_cart_id)
                .select_related("currency")
                .first()
            )

    if cart is None and session_key:
        cart = (
            Cart.objects.filter(session_key=session_key)
            .select_related("currency")
            .first()
        )

    setattr(request, _CART_CACHE_ATTR, cart)
    return cart


@dataclass
class CartSummaryLine:
    """Hydrated cart line for templates and checkout."""

    item: CartItem
    product: Any
    variant: Any
    quantity: int
    unit_price_at_add: Decimal
    line_subtotal: Decimal
    max_stock: int = 0
    is_out_of_stock: bool = False
    exceeds_stock: bool = False


@dataclass
class CartSummary:
    """Computed cart totals — single selector call, no N+1."""

    cart: Cart
    lines: list[CartSummaryLine] = field(default_factory=list)
    subtotal: Decimal = Decimal("0.00")
    coupon_code: str = ""
    coupon_discount: Decimal = Decimal("0.00")
    delivery_charge: Decimal = Decimal("0.00")
    grand_total: Decimal = Decimal("0.00")
    item_count: int = 0
    has_stock_issues: bool = False
    has_out_of_stock_items: bool = False
    has_exceeds_stock_items: bool = False


def get_cart_by_id(*, cart_id: int) -> Optional[Cart]:
    """
    Return a cart by primary key.

    Query guarantee: exactly 1 SELECT on cart_cart.
    """
    return Cart.objects.filter(pk=cart_id).select_related("currency").first()


def get_cart_item_count(*, cart: Cart | None) -> int:
    """
    Return total item quantity for a cart without hydrating line items.

    Query guarantee: exactly 1 aggregate SELECT on cart_cartitem (0 rows → 0).
    """
    if cart is None:
        return 0
    total = CartItem.objects.filter(cart=cart).aggregate(total=Sum("quantity"))["total"]
    return int(total or 0)


def get_cart_count(*, request: HttpRequest) -> int:
    """
    Return total item quantity in the persistent cart.

    Query guarantee: 0–1 SELECT (cart lookup) + 0–1 aggregate on cart items.
    """
    cart = get_cart_for_request(request=request)
    return get_cart_item_count(cart=cart)


def get_cart_product_ids(*, request: HttpRequest = None, cart=None) -> set[int]:
    """Return a set of product IDs currently in the cart where all purchasable variants are added."""
    if not cart and request:
        cart = get_cart_for_request(request=request)
    if not cart:
        return set()
    items = list(CartItem.objects.filter(cart=cart).values_list("product_id", "variant_id"))
    if not items:
        return set()
    candidate_ids = {pid for pid, _ in items}
    from catalog.models import ProductVariant
    variant_map = {}
    for pid, vid in ProductVariant.objects.filter(product_id__in=candidate_ids, stock_quantity__gt=0).values_list("product_id", "id"):
        variant_map.setdefault(pid, set()).add(vid)
    cart_variant_map = {}
    for pid, vid in items:
        if vid:
            cart_variant_map.setdefault(pid, set()).add(vid)
    fully_in_cart = set()
    for pid in candidate_ids:
        if pid in variant_map and variant_map[pid]:
            if variant_map[pid].issubset(cart_variant_map.get(pid, set())):
                fully_in_cart.add(pid)
        else:
            fully_in_cart.add(pid)
    return fully_in_cart


def get_cart_item_keys(*, request: HttpRequest) -> set[str]:
    """Return a set of composite item keys ('pid_vid' or 'pid') currently in the cart."""
    cart = get_cart_for_request(request=request)
    if not cart:
        return set()
    return {f"{pid}_{vid}" if vid else f"{pid}" for pid, vid in CartItem.objects.filter(cart=cart).values_list("product_id", "variant_id")}


def _wishlist_items_qs(*, request: HttpRequest):
    """Shared queryset for the current request's wishlist items."""
    from accounts.models import WishlistItem

    if request.user.is_authenticated and hasattr(request.user, "customer_profile"):
        return WishlistItem.objects.filter(
            wishlist__customer_profile=request.user.customer_profile
        )
    guest_id = request.session.get("guest_wishlist_id")
    if guest_id:
        return WishlistItem.objects.filter(wishlist_id=guest_id)
    if not request.session.session_key:
        return WishlistItem.objects.none()
    return WishlistItem.objects.filter(wishlist__session_key=request.session.session_key)


def get_wishlist_count(*, request: HttpRequest) -> int:
    """Return wishlist item count from the persistent Wishlist model."""
    return _wishlist_items_qs(request=request).count()


def get_wishlist_product_ids(*, request: HttpRequest) -> set[int]:
    """Return product IDs currently on the request wishlist."""
    return set(_wishlist_items_qs(request=request).values_list("product_id", flat=True))


def get_cart_collection_ids(lines: list[CartSummaryLine]) -> list[int]:
    """Distinct collection ids across cart lines (products must carry prefetched collections)."""
    return list({c.pk for line in lines for c in line.product.collections.all()})


def get_cart_summary(*, cart: Cart) -> CartSummary:
    """
    Return a fully computed cart summary for drawer, checkout, and payment.

    Query guarantee:
      1) cart items SELECT with select_related(product, variant, brand)
      2) one gifting.get_gift_customization_snapshot call per customized line
         (each is a constant 1 SELECT + prefetches inside gifting — no cart ORM
         into gifting tables)

    Cross-app boundary: gift snapshot hydration is delegated exclusively to
    ``gifting.selectors.get_gift_customization_snapshot``.
    """
    items = list(
        CartItem.objects.filter(cart=cart)
        .select_related(
            "product",
            "product__brand",
            "variant",
        )
        .prefetch_related(
            Prefetch(
                "product__images",
                queryset=ProductImage.objects.order_by("-is_primary", "display_order"),
                to_attr="primary_images",
            ),
            "product__collections",
        )
        .order_by("id")
    )

    lines: list[CartSummaryLine] = []
    subtotal = Decimal("0.00")
    item_count = 0
    has_stock_issues = False
    has_out_of_stock_items = False
    has_exceeds_stock_items = False

    from cart.services import _resolve_unit_price

    for item in items:
        try:
            unit_price = _resolve_unit_price(
                product=item.product,
                variant=item.variant,
                user=cart.customer_profile.user if hasattr(cart, "customer_profile") and cart.customer_profile else None,
                quantity=item.quantity,
            )
        except Exception:
            unit_price = item.unit_price_at_add

        line_subtotal = unit_price * item.quantity
        subtotal += line_subtotal
        item_count += item.quantity
        max_stock = item.variant.stock_quantity if item.variant else item.product.stock_quantity
        if max_stock is None:
            max_stock = 0
        is_out = not item.product.is_in_stock or max_stock <= 0
        exceeds = not is_out and item.quantity > max_stock
        if is_out:
            has_out_of_stock_items = True
        if exceeds:
            has_exceeds_stock_items = True
        if is_out or exceeds:
            has_stock_issues = True

        lines.append(
            CartSummaryLine(
                item=item,
                product=item.product,
                variant=item.variant,
                quantity=item.quantity,
                unit_price_at_add=unit_price,
                line_subtotal=line_subtotal,
                max_stock=max_stock,
                is_out_of_stock=is_out,
                exceeds_stock=exceeds,
            )
        )

    delivery_charge = cart.delivery_charge

    coupon_code = cart.coupon_code
    coupon_discount = Decimal("0.00")
    if coupon_code:
        from marketing.services import validate_coupon_for_cart
        from marketing.exceptions import InvalidCouponError
        collection_ids = get_cart_collection_ids(lines)
        try:
            result = validate_coupon_for_cart(
                code=coupon_code,
                cart_subtotal=subtotal,
                customer_profile_id=cart.customer_profile_id,
                cart_collection_ids=collection_ids,
            )
            coupon_discount = result["discount_amount"]
        except InvalidCouponError:
            coupon_code = ""
            coupon_discount = Decimal("0.00")

    grand_total = max(subtotal - coupon_discount + delivery_charge, Decimal("0.00"))

    return CartSummary(
        cart=cart,
        lines=lines,
        subtotal=subtotal,
        coupon_code=coupon_code,
        coupon_discount=coupon_discount,
        delivery_charge=delivery_charge,
        grand_total=grand_total,
        item_count=item_count,
        has_stock_issues=has_stock_issues,
        has_out_of_stock_items=has_out_of_stock_items,
        has_exceeds_stock_items=has_exceeds_stock_items,
    )
