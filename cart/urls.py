"""URL routing for the cart app."""

from __future__ import annotations

from django.urls import path

from cart import views

app_name = "cart"

urlpatterns = [
    path("", views.cart_page_view, name="page"),
    path("drawer/", views.cart_drawer_view, name="drawer"),
    path("count/", views.cart_count_view, name="count"),
    path("status/", views.cart_status_view, name="status"),
    path("add/", views.cart_add_view, name="add"),
    path("remove/", views.cart_remove_view, name="remove"),
    path("page/remove/", views.cart_page_remove_view, name="page-remove"),
    path("quantity/", views.cart_quantity_view, name="quantity"),
    path("coupon/apply/", views.cart_coupon_apply_view, name="coupon-apply"),
    path("coupon/remove/", views.cart_coupon_remove_view, name="coupon-remove"),
    path("wishlist/toggle/", views.wishlist_toggle_view, name="wishlist-toggle"),
    path("wishlist/count/", views.wishlist_count_view, name="wishlist-count"),
]
