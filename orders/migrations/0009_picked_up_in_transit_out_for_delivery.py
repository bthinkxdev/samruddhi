"""
Replace the single SHIPPED status with three webhook-driven stages: PICKED_UP,
IN_TRANSIT, OUT_FOR_DELIVERY (DELIVERED already existed). Existing 'shipped' rows
are remapped to 'in_transit' — the closest single equivalent of the old catch-all
status — since we can't know which of the three sub-stages an already-shipped order
was actually at.
"""

from django.db import migrations, models


def migrate_shipped_forward(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    Order.objects.filter(order_status="shipped").update(order_status="in_transit")


def migrate_shipped_backward(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    Order.objects.filter(
        order_status__in=["picked_up", "in_transit", "out_for_delivery"]
    ).update(order_status="shipped")


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0008_new_order_statuses"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="order_status",
            field=models.CharField(
                choices=[
                    ("checkout_pending", "Payment Pending"),
                    ("placed_cod", "COD Awaiting Confirmation"),
                    ("confirmed", "Confirmed"),
                    ("ready_to_ship", "Ready to Ship"),
                    ("picked_up", "Picked Up"),
                    ("in_transit", "In Transit"),
                    ("out_for_delivery", "Out for Delivery"),
                    ("delivered", "Delivered"),
                    ("cancelled", "Cancelled"),
                    ("refunded", "Refunded"),
                ],
                db_index=True,
                default="checkout_pending",
                max_length=20,
                verbose_name="Order status",
            ),
        ),
        migrations.RunPython(migrate_shipped_forward, migrate_shipped_backward),
    ]
