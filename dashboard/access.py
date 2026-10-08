"""Shared access control for the admin dashboard."""

from __future__ import annotations

import functools

from django.contrib.auth.mixins import AccessMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.urls import reverse_lazy

DASHBOARD_GROUPS = ("SuperAdmin", "StoreAdmin")


def user_can_access_dashboard(user) -> bool:
    """True for superusers or members of a dashboard staff group."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=DASHBOARD_GROUPS).exists()


class DashboardAccessMixin(AccessMixin):
    """
    Gate class-based dashboard views behind SuperAdmin/StoreAdmin membership.

    Anonymous users are redirected to the dashboard login; authenticated users
    without a dashboard role get a 403.
    """

    login_url = reverse_lazy("dashboard:login")

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not user_can_access_dashboard(request.user):
            self.raise_exception = True
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)


def dashboard_required(view_func):
    """Decorator gating function-based dashboard views behind staff roles."""

    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(
                request.get_full_path(), login_url=str(reverse_lazy("dashboard:login"))
            )
        if not user_can_access_dashboard(request.user):
            raise PermissionDenied("Insufficient permissions for the dashboard.")
        return view_func(request, *args, **kwargs)

    return wrapper
