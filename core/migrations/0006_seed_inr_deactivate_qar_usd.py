from __future__ import annotations

from decimal import Decimal
from django.db import migrations


def seed_inr_and_deactivate_others(apps, schema_editor) -> None:
    Currency = apps.get_model("core", "Currency")
    SiteSettings = apps.get_model("core", "SiteSettings")

    #deactivate others
    Currency.objects.filter(code__in=["QAR", "USD"]).update(
        is_default=False,
        is_active=False,
    )

    #update or create INR
    inr, _ = Currency.objects.update_or_create(
        code="INR",
        defaults={
            "symbol": "₹",
            "exchange_rate_to_base": Decimal("1.00000000"),
            "is_default": True,
            "is_active": True,
        },
    )

    #update SiteSettings singleton (pk=1)
    SiteSettings.objects.update_or_create(
        pk=1,
        defaults={
            "site_name": "DESERT STAR MOBILE PHONES",
            "default_currency": inr,
            "default_shipping_charge": Decimal("50.00"),
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_currency_is_active_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_inr_and_deactivate_others),
    ]
