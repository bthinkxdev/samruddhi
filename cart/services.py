"""Write operations and business rules for the cart app."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from django.db import transaction
from django.http import HttpRequest

from cart.exceptions import CartItemNotFoundError, InsufficientStockError
from cart.models import Cart, CartItem
from cart.selectors import get_cart_collection_ids, get_cart_for_request, get_cart_summary
from catalog.models import Product, ProductVariant
from catalog.selectors import get_variant_price
from core.selectors import get_default_currency
from delivery.models import City
from delivery.selectors import get_delivery_charge
from marketing.services import validate_coupon_for_cart


def _resolve_unit_price(*, product: Product, variant: Optional[ProductVariant], user: Optional[Any] = None, quantity: int = 1
) -> Decimal:
    """Compute snapshotted unit price from catalog selector."""
    price_data = get_variant_price(
        product_id=product.pk,
        variant_id=variant.pk if variant else None,
        user=user,
        quantity=quantity,
    )
    return Decimal(price_data["price"])


@transaction.atomic
def get_or_create_cart(*, request: HttpRequest) -> Cart:
    """
    Return the persistent cart for the request, creating one when missing.

    Authenticated customers receive a profile-linked cart; guests use session_key.
    """
    if not request.session.session_key:
        request.session.create()

    existing = get_cart_for_request(request=request)
    if existing:
        if not request.user.is_authenticated:
            request.session["guest_cart_id"] = existing.pk
        return existing

    currency = get_default_currency()
    if currency is None:
        raise RuntimeError("No default currency configured.")

    if request.user.is_authenticated and hasattr(request.user, "customer_profile"):
        return Cart.objects.create(
            customer_profile=request.user.customer_profile,
            currency=currency,
        )
    cart = Cart.objects.create(
        session_key=request.session.session_key,
        currency=currency,
    )
    request.session["guest_cart_id"] = cart.pk
    return cart


@transaction.atomic
def add_to_cart(
    *,
    cart: Cart,
    product: Product,
    variant: Optional[ProductVariant] = None,
    quantity: int = 1,
    overwrite: bool = False,
) -> CartItem:
    """
    Add or increment a cart line, or overwrite exactly.
    """
    user = (
        cart.customer_profile.user
        if (cart.customer_profile and cart.customer_profile.user_id)
        else None
    )

    item = CartItem.objects.filter(cart=cart, product=product, variant=variant).first()
    
    if item:
        new_quantity = quantity if overwrite else item.quantity + quantity
    else:
        new_quantity = quantity

    max_stock = variant.stock_quantity if variant else product.stock_quantity
    if new_quantity > max_stock:
        raise InsufficientStockError(f"Only {max_stock} items available in stock.")

    if item:
        unit_price = _resolve_unit_price(product=product, variant=variant, user=user, quantity=new_quantity)
        item.quantity = new_quantity
        item.unit_price_at_add = unit_price
        item.save(update_fields=["quantity", "unit_price_at_add", "updated_at"])
    else:
        unit_price = _resolve_unit_price(product=product, variant=variant, user=user, quantity=quantity)
        item = CartItem.objects.create(
            cart=cart,
            product=product,
            variant=variant,
            quantity=quantity,
            unit_price_at_add=unit_price,
        )

    return item


@transaction.atomic
def remove_cart_item(*, cart: Cart, cart_item_id: int) -> Optional[int]:
    """Remove a line item from the cart. Returns product_id if completely removed."""
    item = CartItem.objects.filter(cart=cart, pk=cart_item_id).first()
    if item:
        product_id = item.product_id
        item.delete()
        if not CartItem.objects.filter(cart=cart, product_id=product_id).exists():
            return product_id
    return None

@transaction.atomic
def adjust_cart_item_quantity(
    *,
    cart: Cart,
    cart_item_id: int,
    delta: int,
) -> Optional[CartItem]:
    """
    Increment or decrement a cart line's quantity by ``delta``.

    Row-locked (``select_for_update``) so rapid +/- clicks never race each
    other into a lost update. Quantity dropping to zero or below deletes the
    line instead of persisting a non-positive quantity.

    Returns:
        The updated CartItem, or None if the line was deleted.

    Raises:
        CartItemNotFoundError: When no matching line exists on this cart.
        InsufficientStockError: When an *increase* would exceed available stock.
    """
    item = CartItem.objects.select_for_update().filter(cart=cart, pk=cart_item_id).first()
    if item is None:
        raise CartItemNotFoundError("Cart item not found.")

    max_stock = item.variant.stock_quantity if item.variant else item.product.stock_quantity
    new_quantity = item.quantity + delta

    if delta < 0 and item.quantity > max_stock:
        new_quantity = max_stock
    elif new_quantity > item.quantity and new_quantity > max_stock:
        # Only *increases* past available stock are blocked.
        raise InsufficientStockError(f"Only {max_stock} items available in stock.")

    if new_quantity < 1:
        new_quantity = 1

    if new_quantity == item.quantity:
        return item

    user = (
        cart.customer_profile.user
        if (cart.customer_profile and cart.customer_profile.user_id)
        else None
    )
    unit_price = _resolve_unit_price(
        product=item.product,
        variant=item.variant,
        user=user,
        quantity=new_quantity,
    )

    item.quantity = new_quantity
    item.unit_price_at_add = unit_price
    item.save(update_fields=["quantity", "unit_price_at_add", "updated_at"])
    return item

@transaction.atomic
def apply_coupon(*, cart: Cart, code: str) -> Cart:
    """
    Validate and apply a coupon via the marketing service boundary.

    Raises:
        InvalidCouponError: Propagated from marketing.services.
    """
    summary = get_cart_summary(cart=cart)
    collection_ids = get_cart_collection_ids(summary.lines)
    result = validate_coupon_for_cart(
        code=code,
        cart_subtotal=summary.subtotal,
        customer_profile_id=cart.customer_profile_id,
        cart_collection_ids=collection_ids,
    )
    cart.coupon_code = result["code"]
    cart.coupon_discount = result["discount_amount"]
    cart.save(update_fields=["coupon_code", "coupon_discount", "updated_at"])
    return cart

@transaction.atomic
def remove_coupon(*, cart: Cart) -> Cart:
    """Clear any applied coupon from the cart."""
    cart.coupon_code = ""
    cart.coupon_discount = Decimal("0.00")
    cart.save(update_fields=["coupon_code", "coupon_discount", "updated_at"])
    return cart


def toggle_wishlist(*, request: HttpRequest, product_id: int) -> bool:
    """
    Toggle a product in the persistent wishlist (DB-backed, guest or authenticated).

    Returns:
        True if product is now in wishlist, False if removed.
    """
    from accounts.models import WishlistItem
    from accounts.subscription_services import (
        add_to_wishlist,
        get_or_create_wishlist,
        remove_from_wishlist,
    )

    wishlist = get_or_create_wishlist(request=request)
    if not request.user.is_authenticated:
        request.session["guest_wishlist_id"] = wishlist.pk
    exists = WishlistItem.objects.filter(wishlist=wishlist, product_id=product_id).exists()
    if exists:
        remove_from_wishlist(wishlist=wishlist, product_id=product_id)
        return False
    add_to_wishlist(wishlist=wishlist, product_id=product_id)
    return True


@transaction.atomic
def merge_carts(*, guest_cart: Cart, user_profile) -> None:
    """Merge the guest cart items into the user's profile cart."""
    user_cart = Cart.objects.filter(customer_profile=user_profile).first()

    if not user_cart:
        guest_cart.customer_profile = user_profile
        guest_cart.session_key = None
        guest_cart.save(update_fields=["customer_profile", "session_key", "updated_at"])
        return

    if guest_cart.pk == user_cart.pk:
        return

    for item in guest_cart.items.all():
        user_item = user_cart.items.filter(
            product=item.product,
            variant=item.variant,
        ).first()
        if user_item:
            user_item.quantity += item.quantity
            user_item.save(update_fields=["quantity", "updated_at"])
            item.delete()
        else:
            item.cart = user_cart
            item.save(update_fields=["cart", "updated_at"])

    guest_cart.delete()


@transaction.atomic
def merge_wishlists(*, guest_wishlist, user_profile) -> None:
    """Merge guest wishlist items into the user's profile wishlist."""
    from accounts.models import Wishlist
    user_wishlist = Wishlist.objects.filter(customer_profile=user_profile).first()
    if not user_wishlist:
        guest_wishlist.customer_profile = user_profile
        guest_wishlist.session_key = None
        guest_wishlist.save(update_fields=["customer_profile", "session_key", "updated_at"])
        return

    if guest_wishlist.pk == user_wishlist.pk:
        return

    for item in guest_wishlist.items.all():
        exists = user_wishlist.items.filter(product=item.product).exists()
        if exists:
            item.delete()
        else:
            item.wishlist = user_wishlist
            item.save(update_fields=["wishlist", "updated_at"])

    guest_wishlist.delete()
