"""Read-only query functions for the checkout app."""

from __future__ import annotations

from typing import Optional

from checkout.models import CheckoutSession, CheckoutSessionStatus


def get_checkout_session_by_id(*, session_id: int) -> Optional[CheckoutSession]:
    """
    Return a checkout session with related cart and address.

    Query guarantee: 1 SELECT with select_related(cart, address, delivery_slot).
    """
    return (
        CheckoutSession.objects.filter(pk=session_id)
        .select_related(
            "cart",
            "cart__currency",
            "cart__destination_city",
            "address",
            "address__city",
            "delivery_slot",
            "customer_profile",
            "order",
        )
        .first()
    )


def get_draft_checkout_for_cart(*, cart_id: int) -> Optional[CheckoutSession]:
    """
    Return the active draft checkout session for a cart.

    Query guarantee: 1 SELECT filtered by cart_id + status=draft.
    """
    return (
        CheckoutSession.objects.filter(
            cart_id=cart_id,
            status=CheckoutSessionStatus.DRAFT,
        )
        .select_related("cart", "address", "delivery_slot")
        .first()
    )
