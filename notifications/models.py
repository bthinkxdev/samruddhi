"""Data layer for the notifications app — models only, no business logic."""

from __future__ import annotations

from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class Notification(TimeStampedModel):
    """In-app notification delivered to a customer."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="User",
        help_text="Recipient of this notification.",
    )
    title = models.CharField(
        max_length=200,
        verbose_name="Title",
        help_text="Short notification headline.",
    )
    body = models.TextField(
        blank=True,
        verbose_name="Body",
        help_text="Full notification message content.",
    )
    is_read = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Is read",
        help_text="When True, the customer has seen this notification.",
    )

    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        indexes = [
            models.Index(
                fields=["user", "is_read"],
                name="notifications_user_read_idx",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title
