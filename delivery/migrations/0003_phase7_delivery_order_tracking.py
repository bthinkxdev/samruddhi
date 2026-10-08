# Generated manually for Phase 7 delivery management.

from __future__ import annotations

from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


def create_default_country_and_assign_cities(apps, schema_editor) -> None:
    Country = apps.get_model("delivery", "Country")
    City = apps.get_model("delivery", "City")
    country, _ = Country.objects.get_or_create(
        code="QA",
        defaults={"name": "Qatar", "is_active": True},
    )
    City.objects.filter(country__isnull=True).update(country=country)


def migrate_slot_types(apps, schema_editor) -> None:
    DeliverySlot = apps.get_model("delivery", "DeliverySlot")
    for slot in DeliverySlot.objects.filter(is_midnight=True):
        slot.slot_type = "midnight"
        slot.save(update_fields=["slot_type"])


class Migration(migrations.Migration):

    dependencies = [
        ("delivery", "0002_phase5_gift_customization"),
    ]

    operations = [
        migrations.CreateModel(
            name="Country",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("name", models.CharField(max_length=120, verbose_name="Country name")),
                ("code", models.CharField(db_index=True, max_length=2, unique=True, verbose_name="ISO country code")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="Is active")),
            ],
            options={
                "verbose_name": "Country",
                "verbose_name_plural": "Countries",
            },
        ),
        migrations.AddField(
            model_name="city",
            name="country",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="cities",
                to="delivery.country",
                verbose_name="Country",
            ),
        ),
        migrations.RunPython(create_default_country_and_assign_cities, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="city",
            name="country",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="cities",
                to="delivery.country",
                verbose_name="Country",
            ),
        ),
        migrations.AddField(
            model_name="city",
            name="delivery_charge_base",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("25.00"),
                max_digits=10,
                verbose_name="Base delivery charge",
            ),
        ),
        migrations.AddField(
            model_name="city",
            name="same_day_cutoff_hour",
            field=models.PositiveSmallIntegerField(
                default=14,
                verbose_name="Same-day cutoff hour",
            ),
        ),
        migrations.AddIndex(
            model_name="city",
            index=models.Index(fields=["country", "is_active"], name="delivery_city_country_idx"),
        ),
        migrations.CreateModel(
            name="DeliveryZone",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("name", models.CharField(max_length=120, verbose_name="Zone name")),
                ("center_latitude", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ("center_longitude", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ("radius_km", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ("postcodes", models.JSONField(blank=True, default=list)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                (
                    "city",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="zones",
                        to="delivery.city",
                    ),
                ),
            ],
            options={
                "verbose_name": "Delivery zone",
                "verbose_name_plural": "Delivery zones",
            },
        ),
        migrations.AddField(
            model_name="deliveryslot",
            name="slot_type",
            field=models.CharField(
                choices=[
                    ("morning", "Morning"),
                    ("evening", "Evening"),
                    ("specific", "Specific"),
                    ("midnight", "Midnight"),
                ],
                db_index=True,
                default="morning",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="deliveryslot",
            name="max_capacity_per_day",
            field=models.PositiveIntegerField(default=100),
        ),
        migrations.RunPython(migrate_slot_types, migrations.RunPython.noop),
        migrations.CreateModel(
            name="DeliverySlotBooking",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("date", models.DateField(db_index=True)),
                ("current_bookings", models.PositiveIntegerField(default=0)),
                (
                    "slot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="slot_bookings",
                        to="delivery.deliveryslot",
                    ),
                ),
            ],
            options={
                "verbose_name": "Delivery slot booking",
                "verbose_name_plural": "Delivery slot bookings",
            },
        ),
        migrations.AddConstraint(
            model_name="deliveryslotbooking",
            constraint=models.UniqueConstraint(fields=("slot", "date"), name="delivery_slot_date_unique"),
        ),
        migrations.AddIndex(
            model_name="deliveryzone",
            index=models.Index(fields=["city", "is_active"], name="delivery_zone_city_idx"),
        ),
        migrations.AddIndex(
            model_name="deliveryslotbooking",
            index=models.Index(fields=["slot", "date"], name="delivery_booking_slot_date_idx"),
        ),
        migrations.AddIndex(
            model_name="country",
            index=models.Index(fields=["is_active"], name="delivery_country_active_idx"),
        ),
    ]
