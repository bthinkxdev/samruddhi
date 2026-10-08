"""HTTP views for the reports app."""

from __future__ import annotations

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

from core.decorators import role_required
from reports.selectors import get_admin_dashboard_summary, get_daily_sales_reports


@role_required("SuperAdmin", "StoreAdmin")
@require_GET
def admin_dashboard_view(request: HttpRequest) -> JsonResponse:
    """Admin reports dashboard summary."""
    summary = get_admin_dashboard_summary()
    sales = get_daily_sales_reports(page=1, page_size=7)
    return JsonResponse({"summary": summary, "recent_sales": sales["results"]})
