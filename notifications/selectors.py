"""Read-only query functions for the notifications app; views must not call the ORM directly."""

from __future__ import annotations

from django.contrib.auth.models import User


def get_unread_notification_count(*, user: User) -> int:
    """
    Return the count of unread notifications for a user.

    Query guarantee: exactly 1 SELECT COUNT on notifications_notification.
    Params:
        user: Django User instance.
    Returns:
        Integer count of unread notifications.
    """
    from notifications.models import Notification

    return Notification.objects.filter(user=user, is_read=False).count()
