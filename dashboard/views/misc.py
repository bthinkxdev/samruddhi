"""Settings (site singleton) and read-only payments views."""

from __future__ import annotations

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from core.models import SiteSettings
from dashboard import forms
from dashboard.access import dashboard_required
from dashboard.views.catalog import _style
from payments.models import PaymentStatus, PaymentTransaction


@dashboard_required
@require_http_methods(["GET", "POST"])
def settings_view(request: HttpRequest) -> HttpResponse:
    """Edit the SiteSettings singleton (pk forced to 1 on save)."""
    instance = SiteSettings.objects.first()
    if request.method == "POST":
        form = forms.SiteSettingsForm(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings saved.")
            return redirect("dashboard:settings")
    else:
        form = forms.SiteSettingsForm(instance=instance)
    _style(form)
    return render(
        request,
        "dashboard/settings.html",
        {"nav_section": "settings", "page_title": "Settings", "form": form},
    )


@dashboard_required
@require_http_methods(["GET"])
def payment_list(request: HttpRequest) -> HttpResponse:
    """Read-only list of payment transactions."""
    from django.db.models import Count, OuterRef, Subquery

    same_order = PaymentTransaction.objects.filter(order_id=OuterRef("order_id"))
    latest_pk = same_order.order_by("-created_at", "-pk").values("pk")[:1]
    attempt_count = same_order.values("order_id").annotate(c=Count("pk")).values("c")[:1]
    qs = (
        PaymentTransaction.objects.select_related("order", "currency")
        .annotate(latest_pk=Subquery(latest_pk), attempt_count=Subquery(attempt_count))
        .order_by("-created_at")
    )
    show_all_attempts = request.GET.get("attempts") == "all"
    if not show_all_attempts:
        qs = qs.filter(pk=Subquery(latest_pk))
    status = request.GET.get("status", "").strip()
    if status:
        qs = qs.filter(status=status)
    query = request.GET.get("q", "").strip()
    if query:
        qs = qs.filter(order__order_number__icontains=query)

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)

    return render(
        request,
        "dashboard/payments/list.html",
        {
            "nav_section": "payments",
            "page_title": "Payments",
            "page_obj": page_obj,
            "objects": page_obj.object_list,
            "statuses": PaymentStatus.choices,
            "current_status": status,
            "search_query": query,
            "show_all_attempts": show_all_attempts,
            "querystring": params.urlencode(),
        },
    )
