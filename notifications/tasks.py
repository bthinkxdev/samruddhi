"""Celery tasks for the notifications app."""

from __future__ import annotations

from celery import shared_task

from notifications.services import (
    create_notification,
    send_email,
    send_order_whatsapp,
    send_sms,
)


@shared_task(name="notifications.tasks.dispatch_sms")
def dispatch_sms(*, phone: str, message: str) -> None:
    """Async Celery wrapper around the send_sms service function."""
    send_sms(phone=phone, message=message)


@shared_task(name="notifications.tasks.dispatch_order_status_notification")
def dispatch_order_status_notification(
    *,
    order_id: int,
    old_status: str,
    new_status: str,
) -> None:
    """
    Send order status updates on the customer's preferred channels.

    Chooses email, SMS, and/or WhatsApp based on CustomerProfile preferences.
    """
    from core.services import get_site_settings
    from orders.models import Order

    order = (
        Order.objects.select_related("customer_profile", "customer_profile__user")
        .prefetch_related("items__product")
        .filter(pk=order_id)
        .first()
    )
    if order is None or order.customer_profile is None:
        return

    profile = order.customer_profile
    user = profile.user
    title = f"Order {order.order_number} update"
    
    items = list(order.items.all())
    product_names = ", ".join([item.product.name for item in items[:3]])
    if len(items) > 3:
        product_names += " and more"
        
    status_messages = {
        "checkout_pending": f"Your order ({order.order_number}) is awaiting payment. Complete your payment to confirm it.",
        "placed_cod": f"Thanks for your Cash on Delivery order ({order.order_number})! Our team will contact you shortly to confirm it.",
        "confirmed": f"Your order ({order.order_number}) has been confirmed.",
        "ready_to_ship": f"Your order ({order.order_number}) is packed and ready for dispatch.",
        "picked_up": f"Your package ({order.order_number}) has been picked up by Delhivery.",
        "in_transit": f"Your shipment ({order.order_number}) is on the way.",
        "out_for_delivery": f"Your order ({order.order_number}) is out for delivery today! Please make sure someone is available to receive it.",
        "delivered": f"Your order ({order.order_number}) has been delivered successfully! We hope you love your new jewellery. (You can now leave a review in your dashboard!).",
        "cancelled": f"Your order ({order.order_number}) has been cancelled.",
        "refunded": f"Your order ({order.order_number}) has been refunded."
    }
    
    body = status_messages.get(new_status, f"Your order status changed from {old_status} to {new_status}.")
    body += f"\n\nBest regards,\nThe {get_site_settings().site_name} Team"

    if profile.notify_via_email and user.email:
        send_email(email=user.email, subject=title, message=body)

    if profile.phone:
        if profile.notify_via_sms:
            send_sms(phone=profile.phone, message=body)
        if profile.notify_via_whatsapp:
            send_order_whatsapp(order=order, event=new_status, phone=profile.phone)


@shared_task(name="notifications.tasks.dispatch_new_order_admin_notification")
def dispatch_new_order_admin_notification(*, order_id: int) -> None:
    """
    Alert the store's configured order-notification address that a new order came in.

    Fires once per genuinely-placed order (see orders.services.transition_order_status
    and checkout.services.place_order) — never for abandoned CHECKOUT_PENDING online
    checkouts. Silently does nothing if no address is configured.
    """
    from core.services import get_site_settings
    from orders.models import Order

    site_settings = get_site_settings()
    if not site_settings.order_notification_email:
        return

    order = (
        Order.objects.select_related("customer_profile__user", "currency")
        .prefetch_related("items__product")
        .filter(pk=order_id)
        .first()
    )
    if order is None:
        return

    items = list(order.items.all())
    lines_text = "\n".join(f"- {item.product.name} x{item.quantity}" for item in items)
    currency_code = order.currency.code if order.currency else ""

    subject = f"New order {order.order_number} — {order.get_order_status_display()}"
    body = (
        f"A new order was placed on {site_settings.site_name}.\n\n"
        f"Order: {order.order_number}\n"
        f"Status: {order.get_order_status_display()}\n"
        f"Customer: {order.customer_display_name}\n"
        f"Total: {currency_code} {order.total_amount}\n\n"
        f"Items:\n{lines_text}\n\n"
        f"View in dashboard for full details."
    )

    send_email(email=site_settings.order_notification_email, subject=subject, message=body)


@shared_task(name="notifications.tasks.dispatch_order_confirmation_notification")
def dispatch_order_confirmation_notification(*, order_id: int) -> None:
    """
    Send an order confirmation email / notification right after the order is placed.
    """
    from orders.models import Order
    from django.urls import reverse
    from core.services import get_site_settings

    order = (
        Order.objects.select_related("customer_profile", "customer_profile__user")
        .prefetch_related("items__product")
        .filter(pk=order_id)
        .first()
    )
    if order is None or order.customer_profile is None:
        return

    profile = order.customer_profile
    user = profile.user
    is_confirmed = (order.order_status == "confirmed")
    status_word = "confirmed" if is_confirmed else "received"
    title = f"Order {'Confirmation' if is_confirmed else 'Received'} - {order.order_number}"
    
    tx = order.payment_transactions.filter(status="success").last()
    if not tx:
        tx = order.payment_transactions.last()
    
    is_cod = tx and tx.gateway_key == "cod"
    
    if is_cod:
        payment_text = "Our team will contact you shortly for a quick order confirmation. Your order will be processed after confirmation."
    else:
        payment_text = "Your order is already confirmed and will be processed directly."

    brand = get_site_settings().site_name
    customer_name = user.first_name or user.username
    body = (
        f"Hi {customer_name},\n\n"
        f"Thank you for placing your order with {brand} \n\n"
        f"Order ID:{order.order_number}\n\n"
        f"Your order has been received successfully.\n\n"
        f"{payment_text}\n\n"
        f"We’ll keep you updated with the shipping and tracking details once your order is dispatched.\n\n"
        f"Thank you for choosing {brand}❤️\n\n"
        f"Best regards,\n"
        f"{brand} Team"
    )

    if profile.notify_via_email and user.email:
        send_email(email=user.email, subject=title, message=body)

    if profile.phone:
        if profile.notify_via_sms:
            send_sms(phone=profile.phone, message=f"{brand}: Order {order.order_number} has been {status_word}. Thank you!")
        if profile.notify_via_whatsapp:
            send_order_whatsapp(order=order, event="order_placed", phone=profile.phone)

