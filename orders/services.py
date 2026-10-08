"""Write operations and business rules for the orders app."""

from __future__ import annotations

import random
import string
import uuid
from typing import Optional

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from core import meta_pixel
from orders.exceptions import InvalidOrderStatusTransitionError, OrderNotEditableError
from orders.models import Order, OrderStatus, OrderStatusHistory
from orders.signals import order_status_changed

import logging

logger = logging.getLogger(__name__)

#Address edits are blocked once the order is physically with the courier or
#resolved — editing our snapshot at that point wouldn't redirect the actual
#shipment and would mislead an admin into thinking it did.
ADDRESS_EDITABLE_STATUSES: frozenset[str] = frozenset({
    OrderStatus.CHECKOUT_PENDING,
    OrderStatus.PLACED_COD,
    OrderStatus.CONFIRMED,
    OrderStatus.READY_TO_SHIP,
})

#Admin-manual transitions only. The webhook (delhivery.views.delhivery_webhook)
#always calls transition_order_status with force=True, so it is never limited by
#this map — PICKED_UP / IN_TRANSIT / OUT_FOR_DELIVERY / DELIVERED are reachable only
#through the webhook, never listed here, so an admin can never select them from the
#dashboard's transition dropdown (which is built from this same map).
ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    OrderStatus.CHECKOUT_PENDING: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.PLACED_COD: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.READY_TO_SHIP, OrderStatus.CANCELLED},
    OrderStatus.READY_TO_SHIP: {OrderStatus.CANCELLED},
    OrderStatus.PICKED_UP: set(),
    OrderStatus.IN_TRANSIT: set(),
    OrderStatus.OUT_FOR_DELIVERY: set(),
    OrderStatus.DELIVERED: {OrderStatus.REFUNDED},
    OrderStatus.CANCELLED: {OrderStatus.REFUNDED},
    OrderStatus.REFUNDED: set(),
}

#Fulfillment rank used by the Delhivery webhook to reject out-of-order/backward scan
#events (e.g. a stale "in transit" push arriving after "delivered" already landed).
#CANCELLED/REFUNDED are absorbing states and intentionally excluded — a courier
#RTO/cancel can legitimately happen from any rank.
ORDER_STATUS_RANK: dict[str, int] = {
    OrderStatus.CONFIRMED: 1,
    OrderStatus.READY_TO_SHIP: 2,
    OrderStatus.PICKED_UP: 3,
    OrderStatus.IN_TRANSIT: 4,
    OrderStatus.OUT_FOR_DELIVERY: 5,
    OrderStatus.DELIVERED: 6,
}

#Statuses that represent a real, uncancelled sale — for revenue/order-count
#reporting (reports.services, reports.selectors, dashboard.selectors). Deliberately
#an include-list, not an exclude-list: CHECKOUT_PENDING/PLACED_COD haven't converted
#to a sale yet (nothing paid or confirmed), CANCELLED/REFUNDED had the sale reversed.
#An include-list also means a future new status defaults to NOT counting as revenue
#until someone deliberately adds it here, rather than silently counting by default.
REVENUE_ORDER_STATUSES: frozenset[str] = frozenset(ORDER_STATUS_RANK.keys())


from django.db.models import Max, IntegerField
from django.db.models.functions import Cast, Substr

def generate_order_number() -> str:
    """Return a unique sequential order number starting from #3000."""
    max_num = Order.objects.filter(order_number__startswith="#").annotate(
        num_val=Cast(Substr('order_number', 2), output_field=IntegerField())
    ).aggregate(Max('num_val'))['num_val__max']

    if max_num and max_num >= 3000:
        next_num = max_num + 1
    else:
        next_num = 3000

    order_number = f"#{next_num}"
    
    while Order.objects.filter(order_number=order_number).exists():
        next_num += 1
        order_number = f"#{next_num}"
        
    return order_number


@transaction.atomic
def transition_order_status(
    *,
    order: Order,
    new_status: str,
    actor: Optional[User] = None,
    note: str = "",
    send_notifications: bool = True,
    force: bool = False,
) -> Order:
    """
    Validate and apply an order status transition.

    Writes ``OrderStatusHistory`` atomically and emits ``order_status_changed``.
    Notifications listen to the signal — this service never calls them directly.
    """
    old_status = order.order_status
    if new_status == old_status:
        return order

    if not force:
        allowed = ALLOWED_STATUS_TRANSITIONS.get(old_status, set())
        if new_status not in allowed:
            raise InvalidOrderStatusTransitionError(
                f"Cannot transition order from {old_status} to {new_status}."
            )

    order.order_status = new_status
    update_fields = ["order_status", "updated_at"]

    #First time this order becomes a real sale (online payment confirmed, or an
    #existing CHECKOUT_PENDING order switched to COD) — record it once. Direct COD
    #creation sets this itself at Order.objects.create() time instead, since that
    #path never calls this function. Guarded by "is None" because these statuses are
    #one-directional per ALLOWED_STATUS_TRANSITIONS, but staying idempotent costs
    #nothing and protects against a future transition map change re-entering them.
    became_sale = False
    if new_status in (OrderStatus.CONFIRMED, OrderStatus.PLACED_COD) and order.success_at is None:
        order.success_at = timezone.now()
        update_fields.append("success_at")
        became_sale = True

    order.save(update_fields=update_fields)

    if became_sale:
        #server-side Meta Purchase — covers customers who never return to the confirmation
        #page (closed tab after paying, webhook-confirmed payment)
        meta_pixel.dispatch_purchase_event(order)

    OrderStatusHistory.objects.create(
        order=order,
        from_status=old_status,
        to_status=new_status,
        changed_by=actor,
        note=note,
    )

    order_status_changed.send(
        sender=Order,
        order=order,
        old_status=old_status,
        new_status=new_status,
        send_notifications=send_notifications,
    )

    if new_status == OrderStatus.CONFIRMED:
        from orders.plugins import order_confirmed_registry
        transaction.on_commit(lambda: order_confirmed_registry.execute_plugins(order))

        #COD orders already alerted the admin at creation (PLACED_COD) — only notify
        #here the first time an order becomes real, i.e. an online payment succeeding
        #(or an admin manually confirming a still-unpaid CHECKOUT_PENDING order).
        if old_status == OrderStatus.CHECKOUT_PENDING:
            from catalog.services import adjust_stock
            for item in order.items.all():
                target = item.variant if item.variant else item.product
                adjust_stock(target=target, delta=-item.quantity, reason=f"order_confirmed:{order.order_number}")

            from notifications.tasks import dispatch_new_order_admin_notification
            transaction.on_commit(lambda: dispatch_new_order_admin_notification.delay(order_id=order.pk))

    tx = order.payment_transactions.last()
    if tx:
        from payments.models import PaymentStatus
        if new_status == OrderStatus.DELIVERED:
            tx.status = PaymentStatus.SUCCESS
            tx.save(update_fields=["status", "updated_at"])
        elif new_status == OrderStatus.CANCELLED:
            tx.status = PaymentStatus.CANCELLED
            tx.save(update_fields=["status", "updated_at"])
        elif new_status == OrderStatus.REFUNDED:
            tx.status = PaymentStatus.REFUNDED
            tx.save(update_fields=["status", "updated_at"])

    #stock is decremented exactly once, either at PLACED_COD (checkout.services)
    #or here at CONFIRMED (above, when old_status was CHECKOUT_PENDING) — so it
    #must be given back exactly once too. CANCELLED is reachable from any
    #non-pending status (nothing to give back from CHECKOUT_PENDING, since it was
    #never taken). REFUNDED is only restocked when reached straight from
    #DELIVERED — a REFUNDED reached via CANCELLED was already restocked there,
    #and ALLOWED_STATUS_TRANSITIONS makes both CANCELLED and REFUNDED
    #terminal/near-terminal, so neither branch can fire twice for the same order.
    if new_status == OrderStatus.CANCELLED and old_status != OrderStatus.CHECKOUT_PENDING:
        _restock_order_items(order, reason=f"order_cancelled:{order.order_number}")
    elif new_status == OrderStatus.REFUNDED and old_status == OrderStatus.DELIVERED:
        _restock_order_items(order, reason=f"order_refunded:{order.order_number}")

    return order


def _restock_order_items(order: Order, *, reason: str) -> None:
    """Give back the stock reserved for every line on ``order``."""
    from catalog.services import adjust_stock

    for item in order.items.all():
        target = item.variant if item.variant else item.product
        adjust_stock(target=target, delta=item.quantity, reason=reason)


@transaction.atomic
def update_order_delivery_address(
    *, order: Order, data: dict[str, str], actor: Optional[User] = None
) -> Order:
    """
    Update an order's frozen ``delivery_address_snapshot`` with admin-edited
    values.

    Raises:
        OrderNotEditableError: When the order has already shipped or is resolved.
    """
    if order.order_status not in ADDRESS_EDITABLE_STATUSES:
        raise OrderNotEditableError(
            f"Delivery address can no longer be edited — order is {order.get_order_status_display()}."
        )

    snapshot = dict(order.delivery_address_snapshot or {})
    snapshot.update(data)
    order.delivery_address_snapshot = snapshot
    order.save(update_fields=["delivery_address_snapshot", "updated_at"])
    logger.info(
        "Delivery address updated for order %s by %s",
        order.order_number, actor if actor else "system",
    )
    return order
