"""Read-only query functions for the core app; views must not call the ORM directly."""

from __future__ import annotations

from typing import Optional

from django.core.cache import cache

from core.models import Currency

DEFAULT_CURRENCY_CACHE_KEY = "core:default_currency:v1"
DEFAULT_CURRENCY_TTL = 300


def get_default_currency() -> Optional[Currency]:
    """
    Return the default storefront currency.

    Query guarantee: 0–1 SELECT; cached 5 minutes after first hit.
    """
    cached = cache.get(DEFAULT_CURRENCY_CACHE_KEY)
    if cached is not None:
        return cached
    currency = Currency.objects.filter(is_default=True).first()
    if currency is not None:
        cache.set(DEFAULT_CURRENCY_CACHE_KEY, currency, DEFAULT_CURRENCY_TTL)
    return currency


def invalidate_default_currency_cache() -> None:
    """Clear cached default currency after currency mutations."""
    cache.delete(DEFAULT_CURRENCY_CACHE_KEY)


def get_currency_by_code(*, code: str) -> Optional[Currency]:
    """
    Return a currency by its ISO code.

    Query guarantee: exactly 1 SELECT on core_currency filtered by code (indexed).

    Params:
        code: ISO 4217 currency code.
    Returns:
        Currency instance or None.
    """
    return Currency.objects.filter(code=code.upper()).first()
