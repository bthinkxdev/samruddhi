"""
Introduce CHECKOUT_PENDING / PLACED_COD, remove PLACED / PENDING.

CONFIRMED becomes the single trigger for Delhivery AWB creation (see
orders.services.transition_order_status and delhivery.services). Existing rows are
remapped by a data migration:

- 'placed'  -> 'placed_cod'  if the order has a COD PaymentTransaction, else
               'checkout_pending' (no way to know if it was actually paid otherwise).
- 'pending' -> 'ready_to_ship' if a DelhiveryShipment with a waybill already exists
               (a shipment was already created under the old PENDING-trigger logic),
               else 'confirmed' so the new idempotent AWB-creation task can pick it up
               the next time someone touches the order (a status relabel alone does not
               re-fire the Celery task — see deployment notes for a one-off backfill
               command if you need those retried immediately).

OrderStatusHistory rows are left untouched: they're a plain-text audit log, not
constrained to the OrderStatus choices, so old entries simply keep their original
'placed'/'pending' wording for history.
"""

from django.db import migrations, models


def migrate_statuses_forward(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    PaymentTransaction = apps.get_model("payments", "PaymentTransaction")
    DelhiveryShipment = apps.get_model("delhivery", "DelhiveryShipment")

    cod_order_ids = set(
        PaymentTransaction.objects.filter(gateway_key="cod").values_list("order_id", flat=True)
    )
    shipped_order_ids = set(
        DelhiveryShipment.objects.exclude(waybill_number="")
        .exclude(waybill_number__isnull=True)
        .values_list("order_id", flat=True)
    )

    placed_orders = Order.objects.filter(order_status="placed")
    placed_orders.filter(pk__in=cod_order_ids).update(order_status="placed_cod")
    placed_orders.exclude(pk__in=cod_order_ids).update(order_status="checkout_pending")

    pending_orders = Order.objects.filter(order_status="pending")
    pending_orders.filter(pk__in=shipped_order_ids).update(order_status="ready_to_ship")
    pending_orders.exclude(pk__in=shipped_order_ids).update(order_status="confirmed")


def migrate_statuses_backward(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    #best-effort reverse: cannot distinguish which 'confirmed'/'ready_to_ship' rows
    #originated from the old 'pending' bucket, so only the two new statuses collapse
    #back to their unambiguous predecessor.
    Order.objects.filter(order_status="checkout_pending").update(order_status="placed")
    Order.objects.filter(order_status="placed_cod").update(order_status="placed")


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0007_alter_order_order_status"),
        ("payments", "0001_phase6_cart_checkout_payments"),
        ("delhivery", "0001_initial"),
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
                    ("shipped", "Shipped"),
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
        migrations.RunPython(migrate_statuses_forward, migrate_statuses_backward),
    ]
