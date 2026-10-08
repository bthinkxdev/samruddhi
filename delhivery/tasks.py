"""Celery tasks for the delhivery app."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="delhivery.tasks.create_shipment_for_order")
def create_shipment_for_order(*, order_id: int) -> bool:
    """
    Async wrapper around trigger_shipment_on_confirmed.

    Runs post-commit (see orders.services.transition_order_status) so the blocking
    Delhivery API call never holds the order's DB transaction open.
    """
    from orders.models import Order
    from delhivery.services import trigger_shipment_on_confirmed

    order = Order.objects.filter(pk=order_id).first()
    if order is None:
        logger.error(f"create_shipment_for_order: order {order_id} not found.")
        return False

    return trigger_shipment_on_confirmed(order)
