"""
Seed realistic orders.
"""

from __future__ import annotations

import random
import uuid
from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Address, CustomerProfile
from accounts.services import ensure_customer_profile_for_user, register_customer_email
from accounts.subscription_services import create_subscription, execute_subscription_recurrence
from cart.models import Cart
from cart.services import add_to_cart, apply_coupon
from catalog.models import Product, ProductVariant, VariantType
from checkout.services import create_checkout_session, place_order, update_checkout_session
from core.selectors import get_default_currency
from marketing.models import Coupon, CouponDiscountType
from orders.exceptions import InvalidOrderStatusTransitionError
from orders.models import Order, OrderStatus, OrderStatusHistory, ProofOfDelivery
from orders.services import transition_order_status
from payments.models import PaymentStatus, PaymentTransaction

User = get_user_model()

SEED_KEY_PREFIXES = ("seed-", "recurring-sub-")
SEED_EMAIL_DOMAIN = "seed.theme.test"

#path[0] is a placeholder anchor for index math only — it's never transitioned to.
LINEAR_FLOW = [
    OrderStatus.CHECKOUT_PENDING,
    OrderStatus.CONFIRMED,
    OrderStatus.READY_TO_SHIP,
    OrderStatus.PICKED_UP,
    OrderStatus.IN_TRANSIT,
    OrderStatus.OUT_FOR_DELIVERY,
    OrderStatus.DELIVERED,
]


class Command(BaseCommand):
    help = "Seed orders spanning several ordering modes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete previously seeded orders (and their payments) before seeding.",
        )
        parser.add_argument(
            "--count",
            type=int,
            default=20,
            help="Informational target order count.",
        )

    def handle(self, *args, **options):
        self.rng = random.Random(20260709)
        self.now = timezone.now()

        if options["reset"]:
            self._reset()

        self.currency = get_default_currency()
        if self.currency is None:
            self.stderr.write(self.style.ERROR("No default currency configured. Aborting."))
            return

        products = list(Product.objects.filter(is_active=True).order_by("pk"))
        if not products:
            self.stderr.write(self.style.ERROR("No active products found. Seed the catalog first."))
            return

        self.stdout.write("Setting up prerequisites (stock, slots, customers)...")
        self._ensure_stock(products)
        customers = self._ensure_customers()
        self._ensure_coupons()

        self.stdout.write("Placing orders...")
        placed: list[tuple[Order, OrderStatus, str]] = []

        scenarios = self._build_scenarios(
            products=products,
            customers=customers,
        )

        for idx, sc in enumerate(scenarios, start=1):
            idem = f"seed-{idx:02d}"
            try:
                order = self._place(idem_key=idem, **sc["place"])
            except Exception as exc:  # noqa: BLE001 - report and continue seeding
                self.stderr.write(self.style.WARNING(f"  ! {sc['label']}: {exc}"))
                continue
            placed.append((order, sc["status"], sc["label"]))
            self.stdout.write(f"  + [{order.order_number}] {sc['label']}")

        sub = self._place_subscription(products[0], customers[0])
        if sub is not None:
            placed.append((sub, OrderStatus.DELIVERED, "Subscription recurrence order"))
            self.stdout.write(f"  + [{sub.order_number}] Subscription recurrence order")

        self.stdout.write("Advancing statuses, recording payments, back-dating...")
        for i, (order, target, _label) in enumerate(placed):
            days_ago = i % 14
            created = self.now - timedelta(days=days_ago, hours=self.rng.randint(0, 12))
            Order.objects.filter(pk=order.pk).update(created_at=created)
            order.refresh_from_db()

            is_guest = order.customer_profile_id is None
            initial_statuses = (OrderStatus.CHECKOUT_PENDING, OrderStatus.PLACED_COD)
            if not is_guest and target not in initial_statuses:
                self._advance(order, target, actor=None)
            self._record_payment(order, created)
            if order.order_status == OrderStatus.DELIVERED:
                self._record_pod(order, created)

        self._make_some_low_stock(products)

        self.stdout.write("Aggregating daily report tables...")
        self._aggregate_reports()

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {len(placed)} orders now in the system "
                f"(total orders: {Order.objects.count()})."
            )
        )

    def _reset(self) -> None:
        from checkout.models import CheckoutSession
        CheckoutSession.objects.filter(idempotency_key__startswith="seed-").delete()
        qs = Order.objects.none()
        for prefix in SEED_KEY_PREFIXES:
            qs = qs | Order.objects.filter(idempotency_key__startswith=prefix)
        count = qs.count()
        qs.delete()
        self.stdout.write(self.style.WARNING(f"Reset: deleted {count} previously seeded orders."))

    def _ensure_stock(self, products: list[Product]) -> None:
        Product.objects.filter(is_active=True).update(stock_quantity=250, low_stock_threshold=5)

    def _ensure_variant(self, product: Product) -> ProductVariant:
        variant, _ = ProductVariant.objects.get_or_create(
            product=product,
            variant_type=VariantType.SIZE,
            name="Large",
            defaults={
                "base_price": Decimal("240.00"),
                "sku_suffix": "LG",
                "stock_quantity": 100,
            },
        )
        if variant.stock_quantity < 10:
            variant.stock_quantity = 100
            variant.save(update_fields=["stock_quantity", "updated_at"])
        return variant

    def _ensure_customers(self) -> list[CustomerProfile]:
        specs = [
            ("aisha", "Aisha Rahman", "+97455500001"),
            ("omar", "Omar Khalid", "+97455500002"),
            ("lina", "Lina Haddad", "+97455500003"),
            ("yusuf", "Yusuf Ali", "+97455500004"),
            ("mariam", "Mariam Nasser", "+97455500005"),
            ("khalid", "Khalid Saleh", "+97455500006"),
        ]
        profiles: list[CustomerProfile] = []
        for handle, name, phone in specs:
            email = f"{handle}@{SEED_EMAIL_DOMAIN}"
            profile = CustomerProfile.objects.filter(user__email=email).first()
            if profile is None:
                profile = register_customer_email(email=email, password="seedpass123", name=name)
            profile.phone = phone
            profile.phone_verified = True
            profile.save(update_fields=["phone", "phone_verified", "updated_at"])

            address, _ = Address.objects.get_or_create(
                customer_profile=profile,
                label="Home",
                defaults={
                    "line1": f"{self.rng.randint(1, 99)} Pearl Street",
                    "line2": "Villa 12",
                    "city": "Doha",
                    "is_default": True,
                },
            )
            if profile.default_address_id != address.pk:
                profile.default_address = address
                profile.save(update_fields=["default_address", "updated_at"])
            profiles.append(profile)
        return profiles

    def _ensure_coupons(self) -> None:
        window = {
            "valid_from": self.now - timedelta(days=1),
            "valid_until": self.now + timedelta(days=60),
            "is_active": True,
        }
        Coupon.objects.get_or_create(
            code="SAVE10",
            defaults={
                "discount_type": CouponDiscountType.PERCENTAGE,
                "discount_value": Decimal("10.00"),
                "min_order_value": Decimal("0.00"),
                **window,
            },
        )
        Coupon.objects.get_or_create(
            code="FLAT50",
            defaults={
                "discount_type": CouponDiscountType.FIXED,
                "discount_value": Decimal("50.00"),
                "min_order_value": Decimal("50.00"),
                **window,
            },
        )

    def _build_scenarios(
        self, *, products, customers
    ) -> list[dict]:
        p = products
        c = customers
        future = timezone.localdate() + timedelta(days=2)

        variant_product = p[2 % len(p)]
        variant = self._ensure_variant(variant_product)

        scenarios: list[dict] = [
            {
                "label": "Standard single-item",
                "status": OrderStatus.DELIVERED,
                "place": {"profile": c[0], "lines": [(p[0], None, 1)]},
            },
            {
                "label": "Standard multi-item (3 products)",
                "status": OrderStatus.OUT_FOR_DELIVERY,
                "place": {
                    "profile": c[1],
                    "lines": [(p[1], None, 1), (p[2], None, 2), (p[4], None, 1)],
                },
            },
            {
                "label": "Order with product variant",
                "status": OrderStatus.READY_TO_SHIP,
                "place": {"profile": c[2], "lines": [(variant_product, variant, 1)]},
            },
            {
                "label": "Coupon SAVE10 (percentage) order",
                "status": OrderStatus.DELIVERED,
                "place": {
                    "profile": c[2],
                    "lines": [(p[7 % len(p)], None, 2)],
                    "coupon_code": "SAVE10",
                },
            },
            {
                "label": "Coupon FLAT50 (fixed) on larger order",
                "status": OrderStatus.CONFIRMED,
                "place": {
                    "profile": c[3],
                    "lines": [(p[8 % len(p)], None, 3), (p[9 % len(p)], None, 2)],
                    "coupon_code": "FLAT50",
                },
            },
            {
                "label": "Scheduled delivery with booked slot",
                "status": OrderStatus.OUT_FOR_DELIVERY,
                "place": {
                    "profile": c[4],
                    "lines": [(p[10 % len(p)], None, 1)],
                    "address": c[4].default_address,
                    "delivery_date": future,
                },
            },
            {
                "label": "Guest checkout (no account)",
                "status": OrderStatus.CHECKOUT_PENDING,
                "place": {
                    "profile": None,
                    "session_key": uuid.uuid4().hex,
                    "lines": [(p[12 % len(p)], None, 1)],
                },
            },
            {
                "label": "Bulk quantity order",
                "status": OrderStatus.DELIVERED,
                "place": {"profile": c[0], "lines": [(p[14 % len(p)], None, 10)]},
            },
            {
                "label": "Cancelled order",
                "status": OrderStatus.CANCELLED,
                "place": {"profile": c[1], "lines": [(p[15 % len(p)], None, 1)]},
            },
            {
                "label": "Refunded order",
                "status": OrderStatus.REFUNDED,
                "place": {"profile": c[2], "lines": [(p[16 % len(p)], None, 1)]},
            },
        ]
        return scenarios

    def _place(
        self,
        *,
        idem_key: str,
        profile,
        lines,
        session_key: str = "",
        coupon_code: str | None = None,
        address=None,
        delivery_date=None,
        gateway_key: str = "card",
    ) -> Order:
        existing = Order.objects.filter(idempotency_key=idem_key).first()
        if existing:
            return existing

        if profile is not None:
            cart = Cart.objects.create(customer_profile=profile, currency=self.currency)
        else:
            cart = Cart.objects.create(
                session_key=session_key or uuid.uuid4().hex, currency=self.currency
            )

        for product, variant, qty in lines:
            add_to_cart(
                cart=cart,
                product=product,
                variant=variant,
                quantity=qty,
            )

        if coupon_code and profile is not None:
            apply_coupon(cart=cart, code=coupon_code)

        session = create_checkout_session(
            cart=cart, customer_profile=profile, session_key=session_key or ""
        )
        if address or delivery_date:
            update_checkout_session(
                checkout_session=session,
                address=address,
                delivery_date=delivery_date,
            )

        return place_order(
            checkout_session_id=session.pk,
            idempotency_key=idem_key,
            gateway_key=gateway_key,
            customer_profile=profile,
        )

    def _place_subscription(self, product, profile) -> Order | None:
        try:
            if profile.default_address_id is None:
                return None
            subscription = create_subscription(
                customer_profile=profile,
                product_id=product.pk,
                delivery_address_id=profile.default_address_id,
                frequency="weekly",
                next_run_date=timezone.localdate(),
                quantity=1,
                created_by=profile.user,
            )
            return execute_subscription_recurrence(schedule=subscription.recurring_schedule)
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(self.style.WARNING(f"  ! Subscription order skipped: {exc}"))
            return None

    def _advance(self, order: Order, target: OrderStatus, *, actor) -> None:
        try:
            if target == OrderStatus.CANCELLED:
                transition_order_status(
                    order=order, new_status=OrderStatus.CANCELLED, actor=actor, note="Seed cancel", send_notifications=False
                )
                return
            path = list(LINEAR_FLOW)
            if target == OrderStatus.REFUNDED:
                target_index = len(path) - 1
            else:
                target_index = path.index(target)
            for status in path[1 : target_index + 1]:
                #force=True: PICKED_UP/IN_TRANSIT/OUT_FOR_DELIVERY are webhook-only
                #in production (see orders.services.ALLOWED_STATUS_TRANSITIONS) —
                #seeding simulates the webhook driving these, not an admin.
                transition_order_status(
                    order=order, new_status=status, actor=actor, note="Seed", send_notifications=False, force=True
                )
            if target == OrderStatus.REFUNDED:
                transition_order_status(
                    order=order, new_status=OrderStatus.REFUNDED, actor=actor, note="Seed refund", send_notifications=False
                )
        except (InvalidOrderStatusTransitionError, Exception) as exc:  # noqa: BLE001
            self.stderr.write(
                self.style.WARNING(f"  ~ status fallback for {order.order_number}: {exc}")
            )
            from_status = order.order_status
            Order.objects.filter(pk=order.pk).update(order_status=target)
            OrderStatusHistory.objects.create(
                order=order, from_status=from_status, to_status=target, note="Seed (forced)"
            )
            order.refresh_from_db()

    def _record_payment(self, order: Order, when) -> None:
        if order.payment_transactions.exists():
            return
        gateway = self.rng.choice(["card", "applepay", "gift_voucher", "benefit"])
        if order.order_status in {OrderStatus.CANCELLED}:
            status = PaymentStatus.FAILED
        elif order.order_status in (OrderStatus.CHECKOUT_PENDING, OrderStatus.PLACED_COD):
            status = self.rng.choice([PaymentStatus.PENDING, PaymentStatus.SUCCESS])
        else:
            status = PaymentStatus.SUCCESS
        tx = PaymentTransaction.objects.create(
            order=order,
            gateway_key=gateway,
            amount=order.total_amount,
            currency=order.currency or self.currency,
            status=status,
            external_transaction_id=f"seed_{uuid.uuid4().hex[:12]}",
            metadata={"seed": True},
        )
        PaymentTransaction.objects.filter(pk=tx.pk).update(created_at=when)

    def _record_pod(self, order: Order, when) -> None:
        ProofOfDelivery.objects.get_or_create(
            order=order,
            defaults={
                "delivered_at": when,
                "recipient_name": "Recipient",
                "photo_url": "https://example.com/pod/seed.jpg",
            },
        )

    def _make_some_low_stock(self, products: list[Product]) -> None:
        for product in products[-3:]:
            Product.objects.filter(pk=product.pk).update(stock_quantity=2, low_stock_threshold=5)

    def _aggregate_reports(self) -> None:
        from reports.services import aggregate_daily_reports

        today = timezone.localdate()
        for offset in range(0, 15):
            day = today - timedelta(days=offset)
            try:
                aggregate_daily_reports(report_date=day)
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(self.style.WARNING(f"  ! aggregate {day} failed: {exc}"))
