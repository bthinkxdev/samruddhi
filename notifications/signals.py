from __future__ import annotations

from django.dispatch import receiver

from notifications.tasks import (
    dispatch_order_status_notification,
)
from orders.signals import order_status_changed


@receiver(order_status_changed)
def send_order_status_notification(
    sender,
    *,
    order,
    old_status: str,
    new_status: str,
    **kwargs,
) -> None:
    """
    Listen for order status changes and dispatch async notifications.

    Orders app never imports notifications — this receiver keeps the boundary.
    """
    if not kwargs.get("send_notifications", True):
        return
    dispatch_order_status_notification.delay(
        order_id=order.pk,
        old_status=old_status,
        new_status=new_status,
    )
