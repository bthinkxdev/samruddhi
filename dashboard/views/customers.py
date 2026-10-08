"""Customer and inquiry management."""

from __future__ import annotations

from django.db.models import F
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from accounts.models import CustomerProfile
from core.models import ContactInquiry
from dashboard import forms
from dashboard.access import dashboard_required
from dashboard.views.base import DashboardListView, DashboardUpdateView, DashboardDeleteView


class CustomerListView(DashboardListView):
    model = CustomerProfile
    nav_section = "customers"
    url_basename = "customer"
    singular_name = "Customer"
    plural_name = "Customers"
    search_fields = ["user__email", "user__username", "phone"]
    select_related = ["user"]
    can_create = False
    can_delete = False
    columns = [
        {"label": "Name", "name": "user.get_full_name"},
        {"label": "Email", "name": "user.email"},
        {"label": "Phone", "name": "get_phone"},
        {"label": "Verified", "name": "phone_verified", "type": "bool"},
    ]


class CustomerUpdateView(DashboardUpdateView):
    model = CustomerProfile
    form_class = forms.CustomerProfileForm
    nav_section = "customers"
    url_basename = "customer"
    singular_name = "Customer"


@dashboard_required
def customer_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Customer profile with addresses and recent orders."""
    profile = get_object_or_404(CustomerProfile.objects.select_related("user"), pk=pk)
    context = {
        "nav_section": "customers",
        "page_title": str(profile),
        "profile": profile,
        "addresses": profile.addresses.all(),
        "orders": profile.orders.order_by(F("success_at").desc(nulls_last=True), "-created_at")[:10],
    }
    return render(request, "dashboard/customers/detail.html", context)


class ContactInquiryListView(DashboardListView):
    model = ContactInquiry
    nav_section = "inquiries"
    url_basename = "inquiry"
    singular_name = "Inquiry"
    plural_name = "Inquiries"
    search_fields = ["name", "email", "message"]
    can_create = False
    can_view = True
    can_edit = False
    can_delete = True
    columns = [
        {"label": "Name", "name": "name"},
        {"label": "Email", "name": "email"},
        {"label": "Date", "name": "created_at", "type": "date"},
    ]


class ContactInquiryDeleteView(DashboardDeleteView):
    model = ContactInquiry
    nav_section = "inquiries"
    url_basename = "inquiry"
    singular_name = "Inquiry"


@dashboard_required
def inquiry_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Read full inquiry message."""
    inquiry = get_object_or_404(ContactInquiry, pk=pk)
    context = {
        "nav_section": "inquiries",
        "page_title": f"Inquiry from {inquiry.name}",
        "inquiry": inquiry,
    }
    return render(request, "dashboard/customers/inquiry_detail.html", context)
