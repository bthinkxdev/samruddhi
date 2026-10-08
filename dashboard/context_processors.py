"""Template context processors for the admin dashboard."""

from __future__ import annotations

from django.http import HttpRequest

from notifications.models import Notification


def dashboard_chrome(request: HttpRequest) -> dict:
    """
    Provide topbar notification data for dashboard pages only.

    Kept cheap: returns an empty dict for non-dashboard requests or anonymous
    users so it adds no query cost to the storefront.
    """
    if not request.path.startswith("/dashboard/"):
        return {}
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}

    notifications = list(
        Notification.objects.filter(user=user, is_read=False).order_by("-created_at")[:50]
    )
    unread_count = Notification.objects.filter(user=user, is_read=False).count()
    return {
        "dashboard_notifications": notifications,
        "dashboard_unread_count": unread_count,
    }
