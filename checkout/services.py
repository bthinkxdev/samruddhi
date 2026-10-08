"""Write operations and business rules for the checkout app."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import Address, CustomerProfile
from cart.models import Cart, CartItem
from cart.selectors import get_cart_summary
from catalog.services import adjust_stock
from checkout.exceptions import CheckoutSessionError
from checkout.models import CheckoutSession, CheckoutSessionStatus
from core import meta_pixel

from marketing.models import Coupon
from marketing.services import record_coupon_redemption
from orders.models import Order, OrderItem, OrderStatus
from orders.services import generate_order_number, transition_order_status



@transaction.atomic
def create_checkout_session(
    *,
    cart: Cart,
    customer_profile: Optional[CustomerProfile] = None,
    session_key: str = "",
) -> CheckoutSession:
    """
    Start or return the draft checkout session for a cart.

    Query guarantee: 0–1 SELECT + 0–1 INSERT.
    """
    existing = CheckoutSession.objects.filter(
        cart=cart,
        status=CheckoutSessionStatus.DRAFT,
    ).first()
    if existing:
        return existing
    return CheckoutSession.objects.create(
        cart=cart,
        customer_profile=customer_profile,
        session_key=session_key,
    )


@transaction.atomic
def update_checkout_session(
    *,
    checkout_session: CheckoutSession,
    address: Optional[Address] = None,
    delivery_date: Optional[date] = None,

    invoice_details: Optional[dict[str, Any]] = None,
) -> CheckoutSession:
    """Persist checkout step data on the session."""
    if address is not None:
        checkout_session.address = address
    if delivery_date is not None:
        checkout_session.delivery_date = delivery_date

    if invoice_details is not None:
        checkout_session.invoice_details = invoice_details
    checkout_session.save()
    return checkout_session


def _order_item_variant_snapshot(*, product, variant) -> tuple[str, str]:
    """(variant_name, variant_sku) captured at purchase time so order history
    survives a later variant edit/delete — see OrderItem.variant_name/variant_sku."""
    if variant is None:
        return "", ""
    sku = f"{product.sku}-{variant.sku_suffix}" if variant.sku_suffix else product.sku
    return variant.name, sku


def _sync_checkout_pending_order(
    *, order: Order, session: CheckoutSession, gateway_key: str, idempotency_key: str
) -> Order:
    """
    Sync an existing CHECKOUT_PENDING order with the current cart and update its payment method.
    This handles the case where a customer abandons a checkout, updates their cart, and checks out again.
    """
    summary = get_cart_summary(cart=session.cart)
    if not summary.lines:
        raise CheckoutSessionError("Cart is empty.")

    order.items.all().delete()

    for line in summary.lines:
        variant_name, variant_sku = _order_item_variant_snapshot(product=line.product, variant=line.variant)
        OrderItem.objects.create(
            order=order,
            product=line.product,
            variant=line.variant,
            variant_name=variant_name,
            variant_sku=variant_sku,
            quantity=line.quantity,
            unit_price=line.unit_price_at_add,
        )

    order.subtotal = summary.subtotal
    order.coupon_discount = summary.coupon_discount
    order.delivery_charge = summary.delivery_charge
    order.total_amount = summary.grand_total
    order.idempotency_key = idempotency_key
    order.save(
        update_fields=["subtotal", "coupon_discount", "delivery_charge", "total_amount", "idempotency_key", "updated_at"]
    )

    if gateway_key == "cod":
        for item in order.items.all():
            target = item.variant if item.variant else item.product
            adjust_stock(target=target, delta=-item.quantity, reason=f"order:{idempotency_key}")
            
        transition_order_status(
            order=order,
            new_status=OrderStatus.PLACED_COD,
            note="Payment method switched to Cash on Delivery",
            send_notifications=False,
            force=True,
        )
        from notifications.tasks import dispatch_new_order_admin_notification
        transaction.on_commit(lambda: dispatch_new_order_admin_notification.delay(order_id=order.pk))
    else:
        if order.order_status != OrderStatus.CHECKOUT_PENDING:
            order.order_status = OrderStatus.CHECKOUT_PENDING
            order.save(update_fields=["order_status", "updated_at"])

    session.idempotency_key = idempotency_key
    session.save(update_fields=["idempotency_key", "updated_at"])

    return order


@transaction.atomic
def place_order(
    *,
    checkout_session_id: int,
    idempotency_key: str,
    gateway_key: str,
    customer_profile: Optional[CustomerProfile] = None,
    is_guest_checkout: bool = False,
) -> Order:
    """
    Atomically place an order from a checkout session.

    Idempotent: calling twice with the same ``idempotency_key`` returns the
    existing Order rather than creating a duplicate.

    Reserves delivery slot capacity before finalizing the order.

    Stock is decremented via ``catalog.services.adjust_stock`` (select_for_update).

    ``gateway_key`` decides the initial order status: COD orders start at
    PLACED_COD (awaiting admin confirmation); every other gateway starts at
    CHECKOUT_PENDING (awaiting payment) so abandoned online checkouts are
    distinguishable from real orders and never trigger a Delhivery shipment.

    Raises:
        CheckoutSessionError: When session is not in a placeable state.
        InsufficientStockError: When stock is insufficient (no oversell).
        SlotFullyBookedError: When the chosen delivery slot is at capacity.
    """
    # "address" and "order" are deliberately excluded from select_related: both are
    # nullable FKs, and PostgreSQL rejects FOR UPDATE across a LEFT OUTER JOIN on the
    # nullable side. They're read separately below via session.address / session.order.
    session = (
        CheckoutSession.objects.select_for_update()
        .select_related(
            "cart",
            "cart__currency",
        )
        .filter(pk=checkout_session_id)
        .first()
    )
    if session is None:
        raise CheckoutSessionError("Checkout session not found.")

    if session.order_id and session.order.order_status == OrderStatus.CHECKOUT_PENDING:
        return _sync_checkout_pending_order(
            order=session.order, 
            session=session, 
            gateway_key=gateway_key,
            idempotency_key=idempotency_key
        )

    #a checkout session carries at most one order (CheckoutSession.order is set
    #once and never reassigned). Once that order has moved past CHECKOUT_PENDING
    #— placed as COD directly, or just converted above — any further place_order
    #call for this session (a duplicate click, a client retry after a slow
    #response whose result never reached the browser, ...) must return that same
    #order rather than fall through to creating a second one. This closes a race
    #the idempotency_key check below can't: _reuse_checkout_pending_order_as_cod
    #deliberately leaves the order's idempotency_key untouched, so a retry
    #carrying the COD submission's key won't match it by key lookup, and
    #session.status only flips to COMPLETED later, in a separate transaction
    #(payments.services.confirm_payment_success) outside this function's lock.
    if session.order_id and session.order.order_status != OrderStatus.CHECKOUT_PENDING:
        return session.order

    existing = Order.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        return existing

    if session.status == CheckoutSessionStatus.COMPLETED and session.order_id:
        if session.idempotency_key == idempotency_key:
            return session.order
        raise CheckoutSessionError("Checkout session already completed.")

    if session.status != CheckoutSessionStatus.DRAFT:
        raise CheckoutSessionError("Checkout session is not in draft status.")

    summary = get_cart_summary(cart=session.cart)
    if not summary.lines:
        raise CheckoutSessionError("Cart is empty.")

    # Stock will be reduced only when the order is successfully placed (PLACED_COD or payment success)

    address_snapshot: dict[str, Any] = {}
    if session.address_id:
        addr = session.address
        address_snapshot = {
            "name": addr.customer_profile.user.get_full_name() if (addr.customer_profile and addr.customer_profile.user) else "",
            "email": addr.customer_profile.user.email if (addr.customer_profile and addr.customer_profile.user) else "",
            "phone": addr.customer_profile.phone if addr.customer_profile else "",
            "label": addr.label,
            "line1": addr.line1,
            "line2": addr.line2,
            "city": addr.city,
            "state": getattr(addr, "state", "") or "",
            "pincode": getattr(addr, "pincode", "") or "",
        }

    initial_status = OrderStatus.PLACED_COD if gateway_key == "cod" else OrderStatus.CHECKOUT_PENDING

    invoice_details = dict(session.invoice_details or {})
    invoice_details["is_guest_checkout"] = is_guest_checkout

    try:
        order = Order.objects.create(
            customer_profile=customer_profile,
            cart=session.cart,
            order_number=generate_order_number(),
            idempotency_key=idempotency_key,
            order_status=initial_status,
            #COD orders succeed immediately at placement — this path never goes
            #through transition_order_status, which is where every other route to
            #CONFIRMED/PLACED_COD sets this same field.
            success_at=timezone.now() if initial_status == OrderStatus.PLACED_COD else None,
            delivery_date=session.delivery_date,
            subtotal=summary.subtotal,
            coupon_discount=summary.coupon_discount,
            delivery_charge=summary.delivery_charge,
            total_amount=summary.grand_total,
            currency=session.cart.currency,
            delivery_address_snapshot=address_snapshot,
            invoice_details=invoice_details,
        )
    except IntegrityError:
        return Order.objects.get(idempotency_key=idempotency_key)

    for line in summary.lines:
        variant_name, variant_sku = _order_item_variant_snapshot(product=line.product, variant=line.variant)
        OrderItem.objects.create(
            order=order,
            product=line.product,
            variant=line.variant,
            variant_name=variant_name,
            variant_sku=variant_sku,
            quantity=line.quantity,
            unit_price=line.unit_price_at_add,
        )

    if session.cart.coupon_code:
        coupon = Coupon.objects.filter(
            code__iexact=session.cart.coupon_code.strip(),
            is_active=True,
        ).first()
        if coupon is not None and customer_profile is not None:
            record_coupon_redemption(
                coupon_id=coupon.pk,
                customer_profile_id=customer_profile.pk,
                order_id=order.pk,
            )

    session.order = order
    session.idempotency_key = idempotency_key
    session.customer_profile = customer_profile
    session.save(
        update_fields=[
            "order",
            "idempotency_key",
            "customer_profile",
            "updated_at",
        ]
    )

    if initial_status == OrderStatus.PLACED_COD:
        for line in summary.lines:
            target = line.variant if line.variant else line.product
            adjust_stock(target=target, delta=-line.quantity, reason=f"order:{idempotency_key}")

        from notifications.tasks import dispatch_new_order_admin_notification
        transaction.on_commit(lambda: dispatch_new_order_admin_notification.delay(order_id=order.pk))
        meta_pixel.dispatch_purchase_event(order)

    return order
