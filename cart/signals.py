"""Cross-app signal handlers for the cart app (side effects only)."""

from __future__ import annotations

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from cart.models import Cart
from cart.services import merge_carts, merge_wishlists
from accounts.models import Wishlist


@receiver(user_logged_in)
def merge_guest_cart_and_wishlist_on_login(sender, request, user, **kwargs) -> None:
    """When a user logs in, merge their guest cart and wishlist into their profile."""
    customer_profile = getattr(user, "customer_profile", None)
    if not customer_profile:
        from accounts.models import CustomerProfile
        customer_profile = CustomerProfile.objects.filter(user=user).first()
    if not customer_profile:
        return

    guest_cart = None
    guest_cart_id = request.session.get("guest_cart_id")
    if guest_cart_id:
        guest_cart = Cart.objects.filter(pk=guest_cart_id).first()
    if not guest_cart and request.session.session_key:
        guest_cart = Cart.objects.filter(session_key=request.session.session_key).first()

    if guest_cart:
        merge_carts(guest_cart=guest_cart, user_profile=customer_profile)
        if "guest_cart_id" in request.session:
            del request.session["guest_cart_id"]

    if hasattr(request, "_theme_resolved_cart"):
        delattr(request, "_theme_resolved_cart")

    guest_wishlist_id = request.session.get("guest_wishlist_id")
    if guest_wishlist_id:
        guest_wishlist = Wishlist.objects.filter(pk=guest_wishlist_id).first()
        if guest_wishlist:
            merge_wishlists(guest_wishlist=guest_wishlist, user_profile=customer_profile)
