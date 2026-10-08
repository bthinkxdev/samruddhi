"""URL routing for the reports app."""

from __future__ import annotations

from django.urls import path

from reports import views

app_name = "reports"

urlpatterns = [
    path("admin/dashboard/", views.admin_dashboard_view, name="admin-dashboard"),
]
