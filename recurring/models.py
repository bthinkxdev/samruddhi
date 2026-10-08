"""Data layer for the shared recurring engine."""

from __future__ import annotations

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from core.models import TimeStampedModel


class RecurrenceFrequency(models.TextChoices):
    """How often a schedule repeats."""

    WEEKLY = "weekly", "Weekly"
    MONTHLY = "monthly", "Monthly"


class RecurrenceStatus(models.TextChoices):
    """Lifecycle of a recurring schedule."""

    ACTIVE = "active", "Active"
    PAUSED = "paused", "Paused"
    CANCELLED = "cancelled", "Cancelled"


class RecurringSchedule(TimeStampedModel):
    """
    Generic recurrence schedule pointing at a repeatable domain object.

    Handlers are registered per ``content_type`` — corporate orders and
    customer subscriptions share this single engine.
    """

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="recurring_schedules",
    )
    object_id = models.PositiveBigIntegerField(db_index=True)
    content_object = GenericForeignKey("content_type", "object_id")

    frequency = models.CharField(
        max_length=20,
        choices=RecurrenceFrequency.choices,
        verbose_name="Frequency",
    )
    next_run_date = models.DateField(db_index=True, verbose_name="Next run date")
    status = models.CharField(
        max_length=20,
        choices=RecurrenceStatus.choices,
        default=RecurrenceStatus.ACTIVE,
        db_index=True,
        verbose_name="Status",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recurring_schedules_created",
        verbose_name="Created by",
    )

    class Meta:
        verbose_name = "Recurring schedule"
        verbose_name_plural = "Recurring schedules"
        indexes = [
            models.Index(
                fields=["status", "next_run_date"],
                name="recurring_status_next_run_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"Schedule #{self.pk} ({self.frequency}, {self.status})"
