"""
Meta (Facebook) Pixel + Conversions API integration.

Browser side: views attach event dicts (see ``event``) to the template context as
``mpx_events`` or queue them in the session (``queue_event``) when the response is a
redirect / HTMX partial. ``base.html`` renders them as JSON and ``static/js/meta_pixel.js``
fires them through ``fbq``.

Server side: ``Purchase`` is the one event that must never depend on the customer's
browser surviving the payment redirect, so it is also sent through the Conversions API
(see ``core.tasks.send_meta_purchase_event``). Browser and server share the event id
``purchase_<order pk>`` so Meta de-duplicates them.

An order counts as a Purchase only when ``Order.success_at`` is set — i.e. online payment
confirmed, or COD placed. ``CHECKOUT_PENDING`` (abandoned / failed payment) never does.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import timedelta
from decimal import Decimal
from typing import Any, Optional

import requests
from django.conf import settings
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

logger = logging.getLogger(__name__)

SESSION_QUEUE_KEY = "mpx_queue"
SESSION_QUEUE_MAX = 10

#Store sells in India (INR, Indian states) — used to normalise Conversions API user data.
DEFAULT_COUNTRY = "in"
DEFAULT_PHONE_COUNTRY_CODE = "91"
FALLBACK_CURRENCY = "INR"

#The confirmation URL is public and re-openable; only fire the browser Purchase for a
#fresh sale so a revisit from another device days later can't count the order twice.
PURCHASE_BROWSER_WINDOW = timedelta(hours=2)

CAPI_TIMEOUT_SECONDS = 10


def pixel_id(site_settings: Any = None) -> str:
    """
    Pixel id from the dashboard (SiteSettings), falling back to the META_PIXEL_ID env var.

    Pixel ids are numeric; anything else yields "" so a bad value can never reach inline JS.
    """
    if site_settings is None:
        from core.services import get_site_settings

        site_settings = get_site_settings()
    value = (site_settings.meta_pixel_id or settings.META_PIXEL_ID).strip()
    return value if value.isdigit() else ""


def capi_access_token(site_settings: Any = None) -> str:
    if site_settings is None:
        from core.services import get_site_settings

        site_settings = get_site_settings()
    return (site_settings.meta_capi_access_token or settings.META_CAPI_ACCESS_TOKEN).strip()


def is_enabled(site_settings: Any = None) -> bool:
    return bool(pixel_id(site_settings))


def is_capi_enabled(site_settings: Any = None) -> bool:
    return is_enabled(site_settings) and bool(capi_access_token(site_settings))


# --------------------------------------------------------------------------- #
# Payload builders
# --------------------------------------------------------------------------- #

def event(
    name: str,
    params: Optional[dict[str, Any]] = None,
    *,
    custom: bool = False,
    event_id: Optional[str] = None,
) -> dict[str, Any]:
    """One browser event. ``custom`` events go through ``fbq('trackCustom', ...)``."""
    payload: dict[str, Any] = {"name": name, "params": params or {}, "custom": custom}
    if event_id:
        payload["event_id"] = event_id
    return payload


def _money(value: Any) -> float:
    return float(Decimal(str(value or 0)).quantize(Decimal("0.01")))


def currency_code(currency: Any = None) -> str:
    """ISO currency code for event payloads — falls back to the store default."""
    code = getattr(currency, "code", "") or ""
    if not code:
        from core.selectors import get_default_currency

        code = getattr(get_default_currency(), "code", "") or ""
    return code.upper() or FALLBACK_CURRENCY


def content_id(product: Any) -> str:
    """Catalog id used in every event — the product pk (variants roll up to their product)."""
    return str(product.pk)


def _collection_name(product: Any) -> str:
    """Name of the product's first collection (Meta ``content_category`` takes one string)."""
    collection = next(iter(product.collections.all()), None)
    return collection.name if collection else ""


def line_content(product: Any, *, quantity: int, price: Any) -> dict[str, Any]:
    return {"id": content_id(product), "quantity": int(quantity), "item_price": _money(price)}


def product_params(
    product: Any,
    *,
    price: Any,
    currency: Any = None,
    quantity: int = 1,
    variant: Any = None,
) -> dict[str, Any]:
    """Params for a single-product event (ViewContent / AddToCart / AddToWishlist ...)."""
    params: dict[str, Any] = {
        "content_type": "product",
        "content_ids": [content_id(product)],
        "content_name": product.name,
        "content_category": _collection_name(product),
        "contents": [line_content(product, quantity=quantity, price=price)],
        "value": _money(Decimal(str(price or 0)) * int(quantity)),
        "currency": currency_code(currency),
    }
    if variant is not None:
        params["variant_name"] = variant.name
    return params


def lines_params(lines: Any, *, value: Any, currency: Any = None) -> dict[str, Any]:
    """
    Params for a multi-line event. ``lines`` is an iterable of objects exposing
    ``product`` / ``quantity`` and either ``unit_price_at_add`` (cart lines) or
    ``unit_price`` (order items).
    """
    contents = []
    num_items = 0
    for line in lines:
        unit_price = getattr(line, "unit_price_at_add", None)
        if unit_price is None:
            unit_price = line.unit_price
        contents.append(line_content(line.product, quantity=line.quantity, price=unit_price))
        num_items += int(line.quantity)
    return {
        "content_type": "product",
        "content_ids": [c["id"] for c in contents],
        "contents": contents,
        "num_items": num_items,
        "value": _money(value),
        "currency": currency_code(currency),
    }


def payment_method_label(gateway_key: str) -> str:
    """``cod`` vs ``online`` — the split Meta reporting needs for Purchase/AddPaymentInfo."""
    return "cod" if gateway_key == "cod" else "online"


def order_params(order: Any) -> dict[str, Any]:
    """Contents / value / identifiers of an order, whatever its payment state."""
    items = list(order.items.select_related("product"))
    params = lines_params(items, value=order.total_amount, currency=order.currency)
    params["order_id"] = order.order_number
    params["checkout_type"] = (order.invoice_details or {}).get("meta_tracking", {}).get(
        "checkout_type", "cart"
    )
    return params


def purchase_params(order: Any) -> dict[str, Any]:
    """Purchase custom_data for a *successful* order (shared by browser + Conversions API)."""
    params = order_params(order)
    tx = (
        order.payment_transactions.filter(status="success").last()
        or order.payment_transactions.last()
    )
    gateway_key = tx.gateway_key if tx else ""
    params["payment_method"] = payment_method_label(gateway_key)
    params["payment_gateway"] = gateway_key
    return params


def purchase_event_id(order: Any) -> str:
    return f"purchase_{order.pk}"


def purchase_page_event(order: Any) -> Optional[dict[str, Any]]:
    """Browser Purchase event, or None unless the order is a real, recent sale."""
    if order.success_at is None:
        return None
    if timezone.now() - order.success_at > PURCHASE_BROWSER_WINDOW:
        return None
    return event("Purchase", purchase_params(order), event_id=purchase_event_id(order))


# --------------------------------------------------------------------------- #
# Session queue — events that must survive a redirect or an HTMX partial response
# --------------------------------------------------------------------------- #

def queue_event(
    request: HttpRequest,
    name: str,
    params: Optional[dict[str, Any]] = None,
    *,
    custom: bool = False,
) -> None:
    if not is_enabled():
        return
    queue = list(request.session.get(SESSION_QUEUE_KEY, []))
    queue.append(event(name, params, custom=custom))
    request.session[SESSION_QUEUE_KEY] = queue[-SESSION_QUEUE_MAX:]


def pop_queued_events(request: HttpRequest) -> list[dict[str, Any]]:
    session = getattr(request, "session", None)
    if session is None or SESSION_QUEUE_KEY not in session:
        return []
    return session.pop(SESSION_QUEUE_KEY)


# --------------------------------------------------------------------------- #
# Browser identifiers captured at checkout so a webhook-confirmed order keeps them
# --------------------------------------------------------------------------- #

def capture_tracking_context(request: HttpRequest, *, checkout_type: str) -> dict[str, str]:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")
    return {
        "fbp": request.COOKIES.get("_fbp", ""),
        "fbc": request.COOKIES.get("_fbc", ""),
        "ip": ip,
        "user_agent": request.META.get("HTTP_USER_AGENT", ""),
        "checkout_type": checkout_type,
    }


# --------------------------------------------------------------------------- #
# Conversions API (server-side Purchase)
# --------------------------------------------------------------------------- #

def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_email(value: str) -> str:
    value = (value or "").strip().lower()
    return _sha256(value) if value else ""


def _hash_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 10:
        digits = DEFAULT_PHONE_COUNTRY_CODE + digits
    return _sha256(digits) if digits else ""


def _hash_text(value: str, *, pattern: str = r"[\W\d_]") -> str:
    cleaned = re.sub(pattern, "", (value or "").strip().lower())
    return _sha256(cleaned) if cleaned else ""


def _build_user_data(order: Any) -> dict[str, Any]:
    snapshot = order.delivery_address_snapshot or {}
    tracking = (order.invoice_details or {}).get("meta_tracking", {})
    profile = order.customer_profile
    user = profile.user if profile else None

    email = snapshot.get("email") or (user.email if user else "")
    phone = snapshot.get("phone") or (profile.phone if profile else "")
    full_name = (snapshot.get("name") or (user.get_full_name() if user else "")).strip()
    first_name, _, last_name = full_name.partition(" ")

    candidates: dict[str, Any] = {
        "em": [_hash_email(email)],
        "ph": [_hash_phone(phone)],
        "fn": [_hash_text(first_name)],
        "ln": [_hash_text(last_name)],
        "ct": [_hash_text(snapshot.get("city", ""))],
        "st": [_hash_text(snapshot.get("state", ""))],
        "zp": [_hash_text(snapshot.get("pincode", ""), pattern=r"[\W_]")],
        "country": [_sha256(DEFAULT_COUNTRY)],
        "external_id": [_sha256(str(profile.pk))] if profile else [""],
        "client_ip_address": tracking.get("ip", ""),
        "client_user_agent": tracking.get("user_agent", ""),
        "fbp": tracking.get("fbp", ""),
        "fbc": tracking.get("fbc", ""),
    }
    return {
        key: value
        for key, value in candidates.items()
        if (value if not isinstance(value, list) else value[0])
    }


def build_capi_purchase_event(order: Any) -> dict[str, Any]:
    tracking = (order.invoice_details or {}).get("meta_tracking", {})
    payload: dict[str, Any] = {
        "event_name": "Purchase",
        "event_time": int(order.success_at.timestamp()),
        "event_id": purchase_event_id(order),
        "action_source": "website",
        "user_data": _build_user_data(order),
        "custom_data": purchase_params(order),
    }
    if tracking.get("source_url"):
        payload["event_source_url"] = tracking["source_url"]
    return payload


def send_purchase_event(*, order_id: int) -> bool:
    """
    POST one Purchase to the Conversions API. Returns True when sent, False when skipped.

    Raises ``requests.RequestException`` on transport / HTTP errors so the Celery task retries.
    The access token goes in the body, never the URL, so it can't leak via exception text.
    """
    from orders.models import Order

    if not is_capi_enabled():
        return False
    order = (
        Order.objects.select_related("customer_profile__user", "currency")
        .filter(pk=order_id)
        .first()
    )
    if order is None or order.success_at is None:
        return False

    body: dict[str, Any] = {
        "data": [build_capi_purchase_event(order)],
        "access_token": capi_access_token(),
    }
    if settings.META_TEST_EVENT_CODE:
        body["test_event_code"] = settings.META_TEST_EVENT_CODE

    url = f"https://graph.facebook.com/{settings.META_API_VERSION}/{pixel_id()}/events"
    response = requests.post(url, json=body, timeout=CAPI_TIMEOUT_SECONDS)
    response.raise_for_status()
    return True


def dispatch_purchase_event(order: Any) -> None:
    """
    Queue the server-side Purchase once the surrounding transaction commits.

    Must never break order placement, so any broker problem is logged and swallowed — the
    browser Purchase still fires on the confirmation page. The small countdown lets the
    checkout view finish saving ``meta_tracking`` onto the order before the task reads it.
    """
    if not is_capi_enabled():
        return

    def _enqueue() -> None:
        try:
            from core.tasks import send_meta_purchase_event

            send_meta_purchase_event.apply_async(kwargs={"order_id": order.pk}, countdown=5)
        except Exception:
            logger.exception("Could not queue Meta Purchase event for order %s", order.pk)

    transaction.on_commit(_enqueue)
