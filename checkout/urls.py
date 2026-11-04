"""URL routing for the checkout app."""

from __future__ import annotations

from django.urls import path

from checkout import views

app_name = "checkout"

urlpatterns = [
    path("", views.checkout_view, name="checkout"),
    path("place-order/", views.checkout_place_order_view, name="place-order"),
    path("whatsapp-otp/send/", views.checkout_whatsapp_otp_send_view, name="whatsapp-otp-send"),
    path(
        "whatsapp-otp/verify/", views.checkout_whatsapp_otp_verify_view, name="whatsapp-otp-verify"
    ),
    path("fix-stock/", views.checkout_fix_stock_view, name="fix-stock"),
    path("update-delivery-charge/", views.checkout_update_delivery_charge_view, name="update-delivery-charge"),
    path("coupon/apply/", views.checkout_coupon_apply_view, name="coupon-apply"),
    path("coupon/remove/", views.checkout_coupon_remove_view, name="coupon-remove"),
    path("confirmation/<int:order_id>/", views.checkout_confirmation_view, name="confirmation"),
    path("pay/stripe/<int:order_id>/", views.stripe_pay_view, name="stripe-pay"),
    path("pay/stripe/return/", views.stripe_return_view, name="stripe-return"),
]
