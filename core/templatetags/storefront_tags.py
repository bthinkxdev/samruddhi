"""Storefront template helpers for currency display."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django import template
from django.utils.html import json_script

from core import meta_pixel

register = template.Library()


def _format_money_amount(value: Decimal) -> str:
    """Format money without trailing .00; keep decimals only when needed."""
    quantized = value.quantize(Decimal("0.01"), ROUND_HALF_UP)
    if quantized == quantized.to_integral_value():
        return f"{int(quantized)}"
    text = f"{quantized:.2f}".rstrip("0").rstrip(".")
    return text


@register.filter
def in_display_currency(amount, currency) -> str:
    """Convert a base-currency amount into the active display currency."""
    if amount is None or amount == "":
        return ""
    if currency is None:
        try:
            return _format_money_amount(Decimal(str(amount)))
        except Exception:
            return str(amount)
    base = Decimal(str(amount))
    rate = Decimal(str(currency.exchange_rate_to_base))
    if rate <= 0:
        return _format_money_amount(base)
    converted = (base / rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
    return _format_money_amount(converted)


@register.simple_tag(takes_context=True)
def meta_pixel_events(context) -> str:
    """
    Render this page's Meta Pixel events as ``<script id="mpx-events">`` JSON.

    Events queued in the session by an earlier redirect come first, then the view's own
    ``mpx_events``. HTMX requests never drain the queue: their markup is often
    discarded by ``hx-select``, so the events would be lost without ever being sent.
    """
    request = context.get("request")
    events = []
    if request is not None and request.headers.get("HX-Request") != "true":
        events.extend(meta_pixel.pop_queued_events(request))
    events.extend(context.get("mpx_events") or [])
    if not events:
        return ""
    return json_script(events, "mpx-events")


@register.simple_tag
def money_label(amount, currency) -> str:
    """Format amount with currency symbol for templates."""
    symbol = getattr(currency, "symbol", "")
    value = in_display_currency(amount, currency)
    return f"{symbol} {value}".strip()
