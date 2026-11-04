import json
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from orders.models import OrderStatus
from payments.adapters.concrete import _get_stripe_credentials
from payments.models import PaymentStatus, PaymentTransaction
from payments.services import confirm_payment_success


class Command(BaseCommand):
    help = "Reconciliation: confirm abandoned Stripe checkouts that actually paid."

    def add_arguments(self, parser):
        parser.add_argument(
            "--minutes",
            type=int,
            default=15,
            help="Recover orders older than this many minutes (default 15)",
        )

    def handle(self, *args, **options):
        import stripe

        _, secret_key = _get_stripe_credentials()
        if not secret_key:
            self.stdout.write(self.style.ERROR("Stripe secret key is not configured."))
            return

        minutes_threshold = options["minutes"]
        time_threshold = timezone.now() - timedelta(minutes=minutes_threshold)

        abandoned_txs = PaymentTransaction.objects.filter(
            order__order_status=OrderStatus.CHECKOUT_PENDING,
            status=PaymentStatus.PENDING,
            gateway_key="stripe",
            created_at__lt=time_threshold,
        )

        recovered_orders_log = []

        for tx in abandoned_txs:
            session_id = tx.external_intent_id
            if not session_id:
                continue

            old_order_status = tx.order.order_status
            old_payment_status = tx.status

            try:
                session = stripe.checkout.Session.retrieve(session_id, api_key=secret_key)
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"Could not retrieve session {session_id}: {exc}"))
                continue

            if session.get("payment_status") not in ("paid", "no_payment_required"):
                continue

            payment_intent_id = str(session.get("payment_intent") or "")

            confirm_payment_success(payment_transaction=tx, external_transaction_id=payment_intent_id)

            tx.refresh_from_db()
            tx.order.refresh_from_db()

            customer_name = tx.order.customer_display_name
            customer_email = ""
            customer_phone = ""

            if tx.order.customer_profile:
                customer_phone = tx.order.customer_profile.phone
                if tx.order.customer_profile.user:
                    customer_email = tx.order.customer_profile.user.email

            snapshot = tx.order.delivery_address_snapshot or {}
            if not customer_email:
                customer_email = snapshot.get("email", "")
            if not customer_phone:
                customer_phone = snapshot.get("phone", "")

            recovered_orders_log.append(
                {
                    "order_number": tx.order.order_number,
                    "transaction_id": tx.id,
                    "customer_name": customer_name,
                    "customer_email": customer_email,
                    "customer_phone": customer_phone,
                    "stripe_checkout_session_id": session_id,
                    "stripe_payment_intent_id": payment_intent_id,
                    "amount": float(tx.amount),
                    "old_order_status": old_order_status,
                    "old_payment_status": old_payment_status,
                    "new_order_status": tx.order.order_status,
                    "new_payment_status": tx.status,
                    "recovery_time": timezone.now().isoformat(),
                }
            )

            self.stdout.write(self.style.SUCCESS(f"Successfully recovered and confirmed order {tx.order.order_number}"))

        if recovered_orders_log:
            import os

            filename = "recovered_stripe_orders.json"
            existing_log = []

            if os.path.exists(filename):
                try:
                    with open(filename, "r") as f:
                        existing_log = json.load(f)
                except (json.JSONDecodeError, ValueError):
                    pass

            existing_log.extend(recovered_orders_log)

            with open(filename, "w") as f:
                json.dump(existing_log, f, indent=4)

            self.stdout.write(self.style.SUCCESS(f"Recovery complete. Log saved to {filename}"))
        else:
            self.stdout.write("Recovery complete. No abandoned paid orders found to recover.")
