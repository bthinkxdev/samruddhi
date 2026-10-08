"""Seed default QAR and USD currencies for the Qatar storefront."""

from __future__ import annotations

from decimal import Decimal

from django.db import migrations


def seed_default_currencies(apps, schema_editor) -> None:
    """Insert base currencies used by the Floward Qatar storefront."""
    Currency = apps.get_model("core", "Currency")

    Currency.objects.update_or_create(
        code="QAR",
        defaults={
            "symbol": "ر.ق",
            "exchange_rate_to_base": Decimal("1.00000000"),
            "is_default": True,
        },
    )
    Currency.objects.update_or_create(
        code="USD",
        defaults={
            "symbol": "$",
            "exchange_rate_to_base": Decimal("3.64000000"),
            "is_default": False,
        },
    )


def remove_default_currencies(apps, schema_editor) -> None:
    """Remove seeded currencies on migration rollback."""
    Currency = apps.get_model("core", "Currency")
    Currency.objects.filter(code__in=["QAR", "USD"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_create_role_groups"),
    ]

    operations = [
        migrations.RunPython(seed_default_currencies, remove_default_currencies),
    ]
