"""Read-only query functions for the reports app."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Count, Sum, F
from django.utils import timezone
from decimal import Decimal

from accounts.models import CustomerProfile
from catalog.models import Product

from orders.models import Order
from orders.services import REVENUE_ORDER_STATUSES
from reports.models import (
    DailyCustomerReport,
    DailyProductPerformance,
    DailySalesReport,
    InventorySnapshot,
)

ADMIN_DASHBOARD_CACHE_KEY = "reports:admin_dashboard:today"
ADMIN_DASHBOARD_CACHE_TTL = 300


def get_daily_sales_reports(
    *,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    page: int = 1,
    page_size: int = 30,
) -> dict[str, Any]:
    """Paginated daily sales from pre-aggregated table only."""
    qs = DailySalesReport.objects.all()
    if start_date:
        qs = qs.filter(report_date__gte=start_date)
    if end_date:
        qs = qs.filter(report_date__lte=end_date)
    paginator = Paginator(qs.order_by("-report_date"), page_size)
    page_obj = paginator.get_page(page)
    return {
        "results": list(page_obj.object_list),
        "page": page_obj.number,
        "total_count": paginator.count,
        "has_next": page_obj.has_next(),
    }


def get_daily_product_performance(
    *,
    report_date: date,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """Product performance for a single day from pre-aggregated table."""
    qs = DailyProductPerformance.objects.filter(report_date=report_date).select_related("product")
    paginator = Paginator(qs.order_by("-revenue"), page_size)
    page_obj = paginator.get_page(page)
    return {"results": list(page_obj.object_list), "page": page_obj.number}


def get_daily_customer_reports(
    *,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    page: int = 1,
    page_size: int = 30,
) -> dict[str, Any]:
    """Paginated customer reports from pre-aggregated table."""
    qs = DailyCustomerReport.objects.all()
    if start_date:
        qs = qs.filter(report_date__gte=start_date)
    if end_date:
        qs = qs.filter(report_date__lte=end_date)
    paginator = Paginator(qs.order_by("-report_date"), page_size)
    page_obj = paginator.get_page(page)
    return {"results": list(page_obj.object_list), "page": page_obj.number}


def get_inventory_snapshots(
    *,
    report_date: date,
    low_stock_only: bool = False,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """Inventory snapshot for a date from pre-aggregated table."""
    qs = InventorySnapshot.objects.filter(report_date=report_date).select_related("product")
    if low_stock_only:
        qs = qs.filter(is_low_stock=True)
    paginator = Paginator(qs.order_by("product__name"), page_size)
    page_obj = paginator.get_page(page)
    return {"results": list(page_obj.object_list), "page": page_obj.number}


def get_live_today_sales_report() -> DailySalesReport:
    """Compute today's sales report on the fly."""
    today = timezone.localdate()
    agg = Order.objects.filter(
        created_at__date=today, order_status__in=REVENUE_ORDER_STATUSES
    ).aggregate(
        order_count=Count("id"),
        revenue=Sum("total_amount"),
        coupon_discount_total=Sum("coupon_discount")
    )
    order_count = agg["order_count"] or 0
    revenue = agg["revenue"] or Decimal("0")
    aov = (revenue / order_count).quantize(Decimal("0.01")) if order_count else Decimal("0")
    
    return DailySalesReport(
        report_date=today,
        order_count=order_count,
        revenue=revenue,
        average_order_value=aov,
        coupon_discount_total=agg["coupon_discount_total"] or Decimal("0")
    )


def get_live_today_customer_report() -> DailyCustomerReport:
    """Compute today's customer report on the fly."""
    today = timezone.localdate()
    new_customers = CustomerProfile.objects.filter(created_at__date=today).count()
    returning = Order.objects.filter(
        created_at__date=today, order_status__in=REVENUE_ORDER_STATUSES
    ).values("customer_profile").distinct().count()
    
    return DailyCustomerReport(
        report_date=today,
        new_customers=new_customers,
        returning_customers=max(returning - new_customers, 0),
        total_active_customers=CustomerProfile.objects.count()
    )


def get_admin_dashboard_summary() -> dict[str, Any]:
    """
    Admin dashboard summary.

    Historical data reads pre-aggregated tables. Today's revenue/order count
    is a deliberate live exception (today cannot be pre-aggregated yet) —
    cached 5 minutes to bound query cost.
    """
    # We've disabled the 5-minute cache so the dashboard updates instantly
    # cached = cache.get(ADMIN_DASHBOARD_CACHE_KEY)
    # if cached is not None:
    #     return cached

    today = timezone.localdate()
    yesterday = today - timedelta(days=1)

    yesterday_report = DailySalesReport.objects.filter(report_date=yesterday).first()
    low_stock_count = Product.objects.filter(
        is_active=True,
        stock_quantity__lte=F("low_stock_threshold"),
        stock_quantity__gt=0,
    ).count()

    today_orders = Order.objects.filter(
        created_at__date=today, order_status__in=REVENUE_ORDER_STATUSES
    )
    today_agg = today_orders.aggregate(
        order_count=Count("id"),
        revenue=Sum("total_amount"),
    )

    summary = {
        "today_revenue": today_agg["revenue"] or 0,
        "today_order_count": today_agg["order_count"] or 0,
        "yesterday_revenue": yesterday_report.revenue if yesterday_report else 0,
        "yesterday_order_count": yesterday_report.order_count if yesterday_report else 0,
        "low_stock_alert_count": low_stock_count,
    }
    cache.set(ADMIN_DASHBOARD_CACHE_KEY, summary, ADMIN_DASHBOARD_CACHE_TTL)
    return summary
