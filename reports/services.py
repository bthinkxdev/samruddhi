"""Nightly aggregation services for the reports app."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, F, Sum
from django.utils import timezone

from accounts.models import CustomerProfile
from catalog.models import Product
from orders.models import Order, OrderItem
from orders.services import REVENUE_ORDER_STATUSES
from reports.models import (
    DailyCustomerReport,
    DailyProductPerformance,
    DailySalesReport,
    InventorySnapshot,
)


def aggregate_daily_reports(*, report_date: date | None = None) -> dict[str, int]:
    """
    Populate all pre-aggregated report tables for a single day.

    Called by nightly Celery beat — admin report views read ONLY these tables
    for historical data (not live Order aggregation).
    """
    if report_date is None:
        report_date = timezone.localdate() - timedelta(days=1)

    orders = Order.objects.filter(
        created_at__date=report_date, order_status__in=REVENUE_ORDER_STATUSES
    )
    agg = orders.aggregate(
        order_count=Count("id"),
        revenue=Sum("total_amount"),
        coupon_discount_total=Sum("coupon_discount"),
    )
    order_count = agg["order_count"] or 0
    revenue = agg["revenue"] or Decimal("0")
    aov = (revenue / order_count).quantize(Decimal("0.01")) if order_count else Decimal("0")

    DailySalesReport.objects.update_or_create(
        report_date=report_date,
        defaults={
            "order_count": order_count,
            "revenue": revenue,
            "average_order_value": aov,
            "coupon_discount_total": agg["coupon_discount_total"] or Decimal("0"),
        },
    )

    product_rows = list(
        OrderItem.objects.filter(
            order__created_at__date=report_date,
            order__order_status__in=REVENUE_ORDER_STATUSES,
        )
        .values("product_id")
        .annotate(
            units_sold=Sum("quantity"),
            revenue=Sum(F("unit_price") * F("quantity")),
        )
    )
    DailyProductPerformance.objects.filter(report_date=report_date).delete()
    for row in product_rows:
        DailyProductPerformance.objects.create(
            report_date=report_date,
            product_id=row["product_id"],
            units_sold=row["units_sold"] or 0,
            revenue=row["revenue"] or Decimal("0"),
        )

    new_customers = CustomerProfile.objects.filter(created_at__date=report_date).count()
    returning = orders.values("customer_profile").distinct().count()
    DailyCustomerReport.objects.update_or_create(
        report_date=report_date,
        defaults={
            "new_customers": new_customers,
            "returning_customers": max(returning - new_customers, 0),
            "total_active_customers": CustomerProfile.objects.count(),
        },
    )

    InventorySnapshot.objects.filter(report_date=report_date).delete()
    low_count = 0
    for product in Product.objects.filter(is_active=True).only(
        "id", "stock_quantity", "low_stock_threshold"
    ):
        is_low = product.stock_quantity <= product.low_stock_threshold
        if is_low:
            low_count += 1
        InventorySnapshot.objects.create(
            report_date=report_date,
            product=product,
            stock_quantity=product.stock_quantity,
            low_stock_threshold=product.low_stock_threshold,
            is_low_stock=is_low,
        )

    return {
        "sales": order_count,
        "products": len(product_rows),
        "low_stock": low_count,
    }


MAX_BACKFILL_DAYS = 60


def missing_report_days() -> int:
    """How many past days (up to yesterday) have no stored daily report yet. One query."""
    yesterday = timezone.localdate() - timedelta(days=1)
    last = DailySalesReport.objects.order_by("-report_date").values_list("report_date", flat=True).first()
    if last is None:
        return 1
    return max(0, min((yesterday - last).days, MAX_BACKFILL_DAYS))


def ensure_daily_reports_current() -> int:
    """
    Fill any missing daily report rows from the last stored day up to yesterday
    (today is always computed live), and always re-run yesterday so late orders /
    status changes from last night are captured.

    """
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)

    last = DailySalesReport.objects.order_by("-report_date").values_list("report_date", flat=True).first()
    start = (last + timedelta(days=1)) if last else yesterday
    if (yesterday - start).days > MAX_BACKFILL_DAYS:
        start = yesterday - timedelta(days=MAX_BACKFILL_DAYS)
    if start > yesterday:
        start = yesterday

    days = 0
    current = start
    while current <= yesterday:
        aggregate_daily_reports(report_date=current)
        current += timedelta(days=1)
        days += 1
    return days


def rebuild_daily_reports(*, start: date, end: date) -> int:
    """Force re-aggregation for every day in [start, end] (capped at yesterday). Returns days rebuilt."""
    yesterday = timezone.localdate() - timedelta(days=1)
    end = min(end, yesterday)
    days = 0
    current = start
    while current <= end:
        aggregate_daily_reports(report_date=current)
        current += timedelta(days=1)
        days += 1
    return days
