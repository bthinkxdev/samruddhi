# Data fix: carts/orders resolve their currency via Currency.is_default
# (core.selectors.get_default_currency), which was left pointing at INR from
# a prior tenant of this codebase. SiteSettings.default_currency separately
# said AED but isn't what carts actually use. This flips the flag so the
# whole stack (cart -> order -> Stripe) is consistent with the real,
# UAE-based business. Non-destructive: no rows deleted, no schema change.

from django.core.cache import cache
from django.db import migrations

#must match core.selectors.DEFAULT_CURRENCY_CACHE_KEY exactly — this migration
#writes straight to the row via the historical model (no app code, including
#core.services.set_default_currency's own cache invalidation, runs here), so
#without this the Redis-backed cache can keep serving the old default for up
#to its 5-minute TTL after this migration applies.
_DEFAULT_CURRENCY_CACHE_KEY = "core:default_currency:v1"


def set_aed_default(apps, schema_editor):
    Currency = apps.get_model("core", "Currency")
    Currency.objects.filter(code="INR").update(is_default=False)
    #AED exists in this dev database already (added outside any migration —
    #there's no earlier migration that creates it), but a fresh database
    #(a clean deploy, or the test database, built from migrations alone)
    #has no AED row at all. get_or_create so this migration is correct on
    #both, not just the one database it happened to be written against.
    Currency.objects.get_or_create(
        code="AED",
        defaults={
            "symbol": "AED",
            "exchange_rate_to_base": "1.00000000",
            "is_default": True,
            "is_active": True,
        },
    )
    Currency.objects.filter(code="AED").update(is_default=True, is_active=True)
    cache.delete(_DEFAULT_CURRENCY_CACHE_KEY)


def set_inr_default(apps, schema_editor):
    Currency = apps.get_model("core", "Currency")
    Currency.objects.filter(code="AED").update(is_default=False)
    Currency.objects.filter(code="INR").update(is_default=True)
    cache.delete(_DEFAULT_CURRENCY_CACHE_KEY)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0027_sitesettings_stripe_publishable_key_and_more"),
    ]

    operations = [
        migrations.RunPython(set_aed_default, set_inr_default),
    ]
