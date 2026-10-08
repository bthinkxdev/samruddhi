"""URL routing for the catalog app."""

from __future__ import annotations

from django.urls import path

from catalog import views

app_name = "catalog"

urlpatterns = [
    path("search/suggest/", views.search_suggestions_view, name="search-suggest"),
    path("rentals/", views.rental_list_view, name="rental-list"),
    path("products/<slug:slug>/", views.pdp_view, name="pdp"),
    path("products/<int:product_id>/review/", views.submit_review_view, name="submit-review"),
    path(
        "products/<int:product_id>/variant-price/",
        views.variant_price_view,
        name="variant-price",
    ),

    path("collections/<slug:collection_slug>/", views.plp_view, name="plp-collection"),
    path("", views.plp_view, name="plp"),
]
