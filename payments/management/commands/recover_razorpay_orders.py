import json
import requests
from datetime import timedelta
from django.utils import timezone
from django.core.management.base import BaseCommand

from payments.models import PaymentTransaction, PaymentStatus
from orders.models import OrderStatus
from payments.adapters.concrete import RazorpayAdapter
from payments.services import confirm_payment_success
from core.models import SiteSettings

class Command(BaseCommand):
    help = "One-time recovery script to confirm old abandoned Razorpay checkouts."

    def add_arguments(self, parser):
        parser.add_argument(
            '--minutes',
            type=int,
            default=15,
            help='Recover orders older than this many minutes (default 15)'
        )

    def handle(self, *args, **options):
        # 1. Get Razorpay credentials
        settings_inst = SiteSettings.objects.first()
        if not settings_inst:
            self.stdout.write(self.style.ERROR("Site settings not found."))
            return
            
        key_id = settings_inst.razorpay_key_id.strip()
        key_secret = settings_inst.razorpay_key_secret.strip()
        
        # 2. Find old abandoned transactions (older than X minutes)
        minutes_threshold = options['minutes']
        time_threshold = timezone.now() - timedelta(minutes=minutes_threshold)
        
        abandoned_txs = PaymentTransaction.objects.filter(
            order__order_status=OrderStatus.CHECKOUT_PENDING,
            status=PaymentStatus.PENDING,
            gateway_key__startswith="razorpay",
            created_at__lt=time_threshold
        )

        adapter = RazorpayAdapter()
        recovered_orders_log = []
        
        for tx in abandoned_txs:
            razorpay_order_id = tx.external_intent_id
            if not razorpay_order_id:
                continue
                
            old_order_status = tx.order.order_status
            old_payment_status = tx.status
            
            # 3. Ask Razorpay for the payments associated with this specific abandoned order
            resp = requests.get(
                f"https://api.razorpay.com/v1/orders/{razorpay_order_id}/payments",
                auth=(key_id, key_secret),
                timeout=10
            )
            
            if resp.status_code == 200:
                payments = resp.json().get("items", [])
                
                for payment in payments:
                    status = payment.get("status")
                    
                    # 4. If the customer actually paid
                    if status in ("authorized", "captured"):
                        payment_id = payment.get("id")
                        
                        # If it's only authorized, manually capture the funds so they aren't refunded
                        if status == "authorized":
                            adapter.capture_payment(
                                razorpay_payment_id=payment_id,
                                amount=tx.amount,
                                currency=payment.get("currency", "INR")
                            )
                        
                        # 5. Confirm the order in our database
                        confirm_payment_success(
                            payment_transaction=tx, 
                            external_transaction_id=payment_id
                        )
                        
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
                        
                        recovered_orders_log.append({
                            "order_number": tx.order.order_number,
                            "transaction_id": tx.id,
                            "customer_name": customer_name,
                            "customer_email": customer_email,
                            "customer_phone": customer_phone,
                            "razorpay_order_id": razorpay_order_id,
                            "razorpay_payment_id": payment_id,
                            "amount": float(tx.amount),
                            "old_order_status": old_order_status,
                            "old_payment_status": old_payment_status,
                            "new_order_status": tx.order.order_status,
                            "new_payment_status": tx.status,
                            "recovery_time": timezone.now().isoformat()
                        })
                        
                        self.stdout.write(self.style.SUCCESS(f"Successfully recovered and confirmed order {tx.order.order_number}"))
                        break
                        
        # 6. Save the log to a single JSON file
        if recovered_orders_log:
            import os
            filename = "recovered_razorpay_orders.json"
            existing_log = []
            
            if os.path.exists(filename):
                try:
                    with open(filename, 'r') as f:
                        existing_log = json.load(f)
                except (json.JSONDecodeError, ValueError):
                    pass
                    
            existing_log.extend(recovered_orders_log)
            
            with open(filename, 'w') as f:
                json.dump(existing_log, f, indent=4)
                
            self.stdout.write(self.style.SUCCESS(f"Recovery complete. Log saved to {filename}"))
        else:
            self.stdout.write("Recovery complete. No abandoned paid orders found to recover.")
