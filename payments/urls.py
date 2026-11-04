"""URL routing for the payments app."""

from __future__ import annotations

from django.urls import path

from payments import views

app_name = "payments"

urlpatterns = [
    # Must precede the generic <str:gateway_key> catch-all below, which would
    # otherwise match "stripe" as a gateway_key and shadow this route.
    path("webhooks/stripe/", views.stripe_webhook_view, name="stripe-webhook"),
    path("webhooks/<str:gateway_key>/", views.payment_webhook_view, name="webhook"),
]
