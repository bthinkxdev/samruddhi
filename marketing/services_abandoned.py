"""Abandoned cart recovery — scans stale carts and dispatches notifications."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from cart.models import Cart, CartItem
from marketing.models import AbandonedCartRecovery
from notifications.services import create_notification, send_email

ABANDONED_CART_HOURS = getattr(settings, "MARKETING_ABANDONED_CART_HOURS", 24)


def scan_abandoned_carts() -> int:
    """
    Find carts with items, no order, stale last update, not yet notified.

    Dispatches recovery email via notifications dispatch pattern.
    """
    cutoff = timezone.now() - timedelta(hours=ABANDONED_CART_HOURS)
    carts = (
        Cart.objects.filter(
            customer_profile__isnull=False,
            updated_at__lte=cutoff,
            items__isnull=False,
        )
        .exclude(recovery_logs__isnull=False)
        .exclude(orders__isnull=False)
        .select_related("customer_profile", "customer_profile__user")
        .distinct()
    )
    sent = 0
    for cart in carts:
        if not CartItem.objects.filter(cart=cart).exists():
            continue
        profile = cart.customer_profile
        if profile is None:
            continue
        user = profile.user
        title = "You left items in your cart"
        body = "Complete your order before your favorites sell out."
        create_notification(user=user, title=title, body=body)
        if profile.notify_via_email and user.email:
            send_email(email=user.email, subject=title, message=body)
        AbandonedCartRecovery.objects.create(cart=cart)
        sent += 1
    return sent
