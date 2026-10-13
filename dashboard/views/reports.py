"""Reports & analytics: charts, tables, CSV export, and manual recompute."""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from dashboard.access import dashboard_required
from reports.selectors import (
    get_admin_dashboard_summary,
    get_daily_customer_reports,
    get_daily_sales_reports,
    get_live_today_sales_report,
    get_live_today_customer_report,
)
from reports.services import aggregate_daily_reports


def _parse_date(value: str, default: date) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return default


@dashboard_required
def reports_view(request: HttpRequest) -> HttpResponse:
    """Analytics dashboard over the pre-aggregated report tables."""
    if "clear" in request.GET:
        request.session.pop("reports_start", None)
        request.session.pop("reports_end", None)
        return redirect("dashboard:reports")

    today = timezone.localdate()
    
    start_str = request.GET.get("start")
    end_str = request.GET.get("end")
    
    if start_str is not None and end_str is not None:
        request.session["reports_start"] = start_str
        request.session["reports_end"] = end_str
    else:
        start_str = request.session.get("reports_start", "")
        end_str = request.session.get("reports_end", "")
        
    start = _parse_date(start_str, today - timedelta(days=31))
    end = _parse_date(end_str, today)
    
    #safeguard against future dates
    if end > today:
        end = today
    if start > end:
        start = end

    sales = get_daily_sales_reports(start_date=start, end_date=end, page=1, page_size=366)
    customers = get_daily_customer_reports(start_date=start, end_date=end, page=1, page_size=366)

    if start <= today <= end:
        sales["results"] = [r for r in sales["results"] if r.report_date != today]
        sales["results"].insert(0, get_live_today_sales_report())
        customers["results"] = [r for r in customers["results"] if r.report_date != today]
        customers["results"].insert(0, get_live_today_customer_report())

    ordered = list(reversed(sales["results"]))
    
    #make chart timeline continuous between start and end
    chart_categories = []
    chart_revenue = []
    chart_orders = []
    
    #create a lookup for quick access
    sales_by_date = {r.report_date: r for r in ordered}
    
    current_date = start
    while current_date <= end:
        chart_categories.append(current_date.strftime("%b %d"))
        if current_date in sales_by_date:
            row = sales_by_date[current_date]
            chart_revenue.append(float(row.revenue) if row.revenue else 0.0)
            chart_orders.append(row.order_count if row.order_count else 0)
        else:
            chart_revenue.append(0.0)
            chart_orders.append(0)
        current_date += timedelta(days=1)
        
    chart = {
        "categories": chart_categories,
        "revenue": chart_revenue,
        "orders": chart_orders,
    }
    total_revenue = sum(float(r.revenue) for r in sales["results"])
    total_orders = sum(r.order_count for r in sales["results"])

    context = {
        "nav_section": "reports",
        "page_title": "Reports",
        "start": start,
        "end": end,
        "summary": get_admin_dashboard_summary(),
        "sales": sales["results"],
        "customers": customers["results"],
        "sales_series": chart,
        "total_revenue": total_revenue,
        "total_orders": total_orders,
    }
    return render(request, "dashboard/reports/index.html", context)


@dashboard_required
def reports_export_csv(request: HttpRequest) -> HttpResponse:
    """Export daily sales in the selected range as CSV."""
    today = timezone.localdate()
    start_str = request.GET.get("start") or request.session.get("reports_start", "")
    end_str = request.GET.get("end") or request.session.get("reports_end", "")
    
    end = _parse_date(end_str, today)
    start = _parse_date(start_str, today - timedelta(days=31))
    
    if end > today:
        end = today
    if start > end:
        start = end
        
    
    from orders.models import OrderItem
    from orders.services import REVENUE_ORDER_STATUSES
    
    items = OrderItem.objects.filter(
        order__created_at__date__gte=start,
        order__created_at__date__lte=end,
        order__order_status__in=REVENUE_ORDER_STATUSES
    ).select_related("order", "product", "order__customer_profile")

    items = items.order_by("-order__created_at", "id")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="sales_details_{start}_{end}.csv"'
    writer = csv.writer(response)
    writer.writerow([
        "Date", "Order ID", "SKU", "HSN Code", "Quantity", 
        "Unit Price", "Total Price", "Customer Name", "Phone", 
        "Address", "City", "State", "Pincode"
    ])
    
    for item in items:
        order = item.order
        addr = order.delivery_address_snapshot or {}
        address_line = f"{addr.get('line1', '')} {addr.get('line2', '')}".strip()
        
        writer.writerow([
            order.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            order.order_number,
            item.product.sku,
            item.product.hsn_code or "",
            item.quantity,
            item.unit_price,
            item.quantity * item.unit_price,
            addr.get("name", ""),
            addr.get("phone", ""),
            address_line,
            addr.get("city", ""),
            addr.get("state", ""),
            addr.get("pincode", ""),
        ])
    return response


@dashboard_required
@require_POST
def reports_recompute(request: HttpRequest) -> HttpResponse:
    """Manually re-run aggregation for a given date (default: yesterday)."""
    target = _parse_date(request.POST.get("date", ""), timezone.localdate() - timedelta(days=1))
    try:
        aggregate_daily_reports(report_date=target)
        messages.success(request, f"Reports recomputed for {target}.")
    except Exception as exc:  # noqa: BLE001 - surface any aggregation failure to admin
        messages.error(request, f"Recompute failed: {exc}")
    return redirect("dashboard:reports")
