"""URL routing for the cms app."""

from __future__ import annotations

from django.urls import path

from cms import views

app_name = "cms"

urlpatterns = [
    path("", views.homepage_view, name="homepage"),
]
