"""URL routing for the checkout app."""

from __future__ import annotations

from django.urls import path

from checkout import views

app_name = "checkout"

urlpatterns = [
    path("", views.checkout_view, name="checkout"),
    path("place-order/", views.checkout_place_order_view, name="place-order"),
    path("fix-stock/", views.checkout_fix_stock_view, name="fix-stock"),
    path("update-delivery-charge/", views.checkout_update_delivery_charge_view, name="update-delivery-charge"),
    path("coupon/apply/", views.checkout_coupon_apply_view, name="coupon-apply"),
    path("coupon/remove/", views.checkout_coupon_remove_view, name="coupon-remove"),
    path("confirmation/<int:order_id>/", views.checkout_confirmation_view, name="confirmation"),
    path("pay/razorpay/<int:order_id>/", views.razorpay_pay_view, name="razorpay-pay"),
    path("pay/razorpay/callback/", views.razorpay_callback_view, name="razorpay-callback"),
]
