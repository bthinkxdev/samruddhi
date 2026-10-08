"""URL routing for the orders app."""

from __future__ import annotations

from django.urls import path

from orders import views

app_name = "orders"

urlpatterns = [
    path("", views.order_list_view, name="list"),
    path("<int:order_id>/", views.order_detail_view, name="detail"),
    path("<int:order_id>/tracking/", views.order_tracking_view, name="tracking"),
]
