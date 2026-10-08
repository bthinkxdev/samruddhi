"""Authentication views for the admin dashboard (staff login/logout)."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache

from dashboard.access import user_can_access_dashboard

User = get_user_model()


def _resolve_username(identifier: str) -> str | None:
    """Accept either a username or an email address at the login form."""
    if "@" in identifier:
        user = User.objects.filter(email__iexact=identifier).order_by("id").first()
        return user.get_username() if user else None
    return identifier


@never_cache
def login_view(request: HttpRequest) -> HttpResponse:
    """Render and process the dashboard staff login form."""
    if user_can_access_dashboard(request.user):
        return redirect("dashboard:home")

    next_url = request.GET.get("next") or request.POST.get("next") or reverse("dashboard:home")

    if request.method == "POST":
        identifier = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        username = _resolve_username(identifier)
        user = authenticate(request, username=username, password=password) if username else None

        if user is None:
            messages.error(request, "Invalid credentials. Please try again.")
        elif not user_can_access_dashboard(user):
            messages.error(request, "This account does not have dashboard access.")
        else:
            auth_login(request, user)
            return redirect(next_url)

    return render(request, "dashboard/login.html", {"next": next_url})


@never_cache
def logout_view(request: HttpRequest) -> HttpResponse:
    """Log the user out and return to the dashboard login page."""
    auth_logout(request)
    return redirect("dashboard:login")
