"""Dashboard home (overview) view."""

from __future__ import annotations

from django.db.models import Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from core.models import Currency
from dashboard import selectors
from dashboard.access import dashboard_required
from reports.models import DailySalesReport
from reports.selectors import get_admin_dashboard_summary


def _pct_delta(current, previous) -> float | None:
    """Percentage change of ``current`` vs ``previous`` (None when incomparable)."""
    current = float(current or 0)
    previous = float(previous or 0)
    if previous == 0:
        return 100.0 if current > 0 else None
    return round((current - previous) / previous * 100, 1)


@dashboard_required
@require_GET
def home_view(request: HttpRequest) -> HttpResponse:
    """Render the dashboard overview with live KPIs, charts and lists."""
    summary = get_admin_dashboard_summary()
    sales_series = selectors.get_sales_series(days=14)
    customer_split = selectors.get_customer_split()
    counts = selectors.get_dashboard_counts()

    from django.utils import timezone
    from reports.selectors import get_live_today_sales_report

    today = timezone.localdate()
    totals = DailySalesReport.objects.exclude(report_date=today).aggregate(
        revenue=Sum("revenue"),
        orders=Sum("order_count"),
    )
    live_today = get_live_today_sales_report()
    
    total_revenue = (totals["revenue"] or 0) + (live_today.revenue or 0)
    total_orders = (totals["orders"] or 0) + (live_today.order_count or 0)
    avg_order_value = (float(total_revenue) / total_orders) if total_orders else 0

    default_currency = Currency.objects.filter(is_default=True).first()

    context = {
        "nav_section": "home",
        "page_title": "Dashboard",
        "currency_symbol": default_currency.symbol if default_currency else "",
        "summary": summary,
        "counts": counts,
        "revenue_delta": _pct_delta(summary["today_revenue"], summary["yesterday_revenue"]),
        "order_delta": _pct_delta(summary["today_order_count"], summary["yesterday_order_count"]),
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "avg_order_value": avg_order_value,
        "top_products": selectors.get_top_products(limit=5),
        "low_stock": selectors.get_low_stock_products(limit=5),
        "recent_orders": selectors.get_recent_orders(limit=6),
        "sales_series": sales_series,
        "customer_split": customer_split,
    }
    return render(request, "dashboard/home.html", context)
