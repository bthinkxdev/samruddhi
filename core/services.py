"""Write operations for core domain singletons and shared configuration."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from core.models import Currency, SiteSettings

SITE_SETTINGS_PK = 1


def get_site_settings() -> SiteSettings:
    """
    Return the singleton SiteSettings row (pk=1 pattern).

    Enforces a single configuration row — admins edit this instance only.
    """
    settings, _ = SiteSettings.objects.get_or_create(pk=SITE_SETTINGS_PK)
    return settings


@transaction.atomic
def create_currency(
    *,
    code: str,
    symbol: str,
    exchange_rate_to_base: Decimal,
    is_default: bool = False,
) -> Currency:
    """Create a currency with normalized uppercase ISO code."""
    if is_default:
        Currency.objects.filter(is_default=True).update(is_default=False)
    currency = Currency.objects.create(
        code=code.upper(),
        symbol=symbol,
        exchange_rate_to_base=exchange_rate_to_base,
        is_default=is_default,
    )
    from core.selectors import invalidate_default_currency_cache

    invalidate_default_currency_cache()
    return currency


@transaction.atomic
def set_default_currency(*, currency: Currency) -> Currency:
    """Promote one currency as storefront default and demote all others."""
    Currency.objects.exclude(pk=currency.pk).filter(is_default=True).update(is_default=False)
    if not currency.is_default:
        currency.is_default = True
        currency.save(update_fields=["is_default", "updated_at"])
    from core.selectors import invalidate_default_currency_cache

    invalidate_default_currency_cache()
    return currency
