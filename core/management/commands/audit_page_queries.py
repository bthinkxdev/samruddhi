"""Systematic query-count audit for key storefront pages."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import connection, reset_queries
from django.test import Client
from django.test.utils import override_settings


@dataclass
class PageAuditResult:
    """Query audit metrics for a single page."""

    page: str
    path: str
    status_code: int
    query_count: int
    duplicate_queries: list[str] = field(default_factory=list)
    slow_queries_ms: list[dict] = field(default_factory=list)
    total_time_ms: float = 0.0


class Command(BaseCommand):
    help = "Audit query counts and duplicates for key storefront pages."

    PAGES = [
        ("homepage", "/"),
        ("plp", "/shop/"),
        ("plp_filtered", "/shop/?bestseller=1&sort=price_asc"),
        ("pdp", None),
        ("gift_builder", None),
        ("cart_drawer", "/cart/drawer/"),
        ("checkout", "/checkout/"),
        ("order_tracking", None),
        ("admin_dashboard", "/reports/admin/dashboard/"),
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default="docs/performance_audit.json",
            help="JSON report output path.",
        )
        parser.add_argument("--slow-ms", type=float, default=50.0, help="Slow query threshold.")

    def handle(self, *args, **options):
        from accounts.models import CustomerProfile
        from accounts.services import register_customer_email
        from catalog.models import Product
        from checkout.services import create_checkout_session, place_order
        from core.models import Currency

        Currency.objects.get_or_create(
            code="QAR",
            defaults={
                "symbol": "QAR",
                "exchange_rate_to_base": "1.00000000",
                "is_default": True,
            },
        )
        product = Product.objects.filter(is_active=True, supports_gift_customization=True).first()
        if product is None:
            product = Product.objects.filter(is_active=True).first()
        if product is None:
            self.stderr.write("No active product found — seed catalog before auditing.")
            return

        profile = CustomerProfile.objects.filter(user__email="audit@example.com").first()
        if profile is None:
            profile = register_customer_email(
                email="audit@example.com",
                password="auditpass123",
                name="Audit User",
            )
        from cart.models import Cart, CartItem

        currency = Currency.objects.get(code="QAR")
        cart = Cart.objects.create(customer_profile=profile, currency=currency)
        CartItem.objects.create(
            cart=cart,
            product=product,
            quantity=1,
            unit_price_at_add=product.base_price,
        )
        session = create_checkout_session(cart=cart, customer_profile=profile)
        order = place_order(
            checkout_session_id=session.pk,
            idempotency_key="audit-order-1",
            gateway_key="card",
            customer_profile=profile,
        )

        paths = {
            "pdp": f"/shop/products/{product.slug}/",
            "gift_builder": f"/gifting/products/{product.slug}/builder/",
            "order_tracking": f"/orders/{order.pk}/tracking/",
        }

        client = Client()
        staff = profile.user
        staff.is_staff = True
        staff.is_superuser = True
        staff.save()
        client.force_login(staff)

        results: list[PageAuditResult] = []
        slow_threshold = options["slow_ms"]

        with override_settings(DEBUG=True):
            for page_name, path in self.PAGES:
                resolved = path or paths[page_name]
                reset_queries()
                start = time.perf_counter()
                response = client.get(resolved)
                elapsed_ms = (time.perf_counter() - start) * 1000

                sql_list = [q["sql"] for q in connection.queries]
                duplicates = sorted({sql for sql in sql_list if sql_list.count(sql) > 1})
                slow = [
                    {"sql": q["sql"][:200], "time_ms": float(q["time"]) * 1000}
                    for q in connection.queries
                    if float(q["time"]) * 1000 >= slow_threshold
                ]

                results.append(
                    PageAuditResult(
                        page=page_name,
                        path=resolved,
                        status_code=response.status_code,
                        query_count=len(connection.queries),
                        duplicate_queries=duplicates[:10],
                        slow_queries_ms=slow[:10],
                        total_time_ms=round(elapsed_ms, 2),
                    )
                )

        output_path = Path(options["output"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps([asdict(r) for r in results], indent=2),
            encoding="utf-8",
        )

        self.stdout.write(self.style.SUCCESS(f"Audit written to {output_path}"))
        for result in results:
            dup_count = len(result.duplicate_queries)
            flag = self.style.WARNING if dup_count else self.style.SUCCESS
            self.stdout.write(
                flag(
                    f"{result.page}: {result.query_count} queries, "
                    f"{dup_count} duplicate SQL patterns, "
                    f"{result.total_time_ms}ms, status={result.status_code}"
                )
            )
