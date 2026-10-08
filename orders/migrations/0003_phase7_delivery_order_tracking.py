# Generated manually for Phase 7 order tracking.

from __future__ import annotations

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


STATUS_MAP = {
    "pending": "received",
    "confirmed": "received",
    "processing": "preparing",
    "shipped": "out_for_delivery",
    "delivered": "delivered",
    "cancelled": "cancelled",
}


def migrate_order_statuses(apps, schema_editor) -> None:
    Order = apps.get_model("orders", "Order")
    for old, new in STATUS_MAP.items():
        Order.objects.filter(order_status=old).update(order_status=new)


class Migration(migrations.Migration):

    dependencies = [
        ("delivery", "0003_phase7_delivery_order_tracking"),
        ("orders", "0002_phase6_cart_checkout_payments"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameModel(
            old_name="OrderLineItem",
            new_name="OrderItem",
        ),
        migrations.RenameField(
            model_name="orderitem",
            old_name="unit_price_at_purchase",
            new_name="unit_price",
        ),
        migrations.AlterModelTable(
            name="orderitem",
            table="orders_orderlineitem",
        ),
        migrations.AlterField(
            model_name="order",
            name="customer_profile",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="orders",
                to="accounts.customerprofile",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="delivery_slot_booking",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="orders",
                to="delivery.deliveryslotbooking",
            ),
        ),
        migrations.RunPython(migrate_order_statuses, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="order",
            name="order_status",
            field=models.CharField(
                choices=[
                    ("received", "Received"),
                    ("preparing", "Preparing"),
                    ("packaging", "Packaging"),
                    ("ready", "Ready"),
                    ("out_for_delivery", "Out for delivery"),
                    ("delivered", "Delivered"),
                    ("cancelled", "Cancelled"),
                    ("refunded", "Refunded"),
                ],
                db_index=True,
                default="received",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="OrderStatusHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("from_status", models.CharField(max_length=20)),
                ("to_status", models.CharField(max_length=20)),
                ("changed_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("note", models.TextField(blank=True)),
                (
                    "changed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="order_status_changes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="status_history",
                        to="orders.order",
                    ),
                ),
            ],
            options={
                "verbose_name": "Order status history",
                "verbose_name_plural": "Order status history",
                "ordering": ["changed_at"],
            },
        ),
        migrations.CreateModel(
            name="ProofOfDelivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("photo_url", models.URLField(blank=True)),
                ("signature_url", models.URLField(blank=True)),
                ("delivered_at", models.DateTimeField()),
                ("recipient_name", models.CharField(max_length=120)),
                (
                    "order",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proof_of_delivery",
                        to="orders.order",
                    ),
                ),
            ],
            options={
                "verbose_name": "Proof of delivery",
                "verbose_name_plural": "Proof of delivery",
            },
        ),
        migrations.AddIndex(
            model_name="orderstatushistory",
            index=models.Index(fields=["order", "changed_at"], name="order_status_hist_order_idx"),
        ),
    ]
