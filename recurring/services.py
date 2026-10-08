"""Shared recurrence processing — one engine for all repeatable domain objects."""

from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from recurring.models import RecurrenceFrequency, RecurrenceStatus, RecurringSchedule
from recurring.registry import get_recurrence_handler


def _advance_next_run_date(*, schedule: RecurringSchedule) -> None:
    """Move next_run_date forward based on frequency."""
    if schedule.frequency == RecurrenceFrequency.WEEKLY:
        schedule.next_run_date += timedelta(days=7)
    else:
        schedule.next_run_date += timedelta(days=30)
    schedule.save(update_fields=["next_run_date", "updated_at"])


@transaction.atomic
def execute_recurrence(*, schedule: RecurringSchedule) -> object:
    """
    Execute one recurrence cycle via the content-type strategy registry.

    Advances ``next_run_date`` after a successful handler run.
    """
    handler = get_recurrence_handler(content_type=schedule.content_type)
    result = handler(schedule=schedule)
    _advance_next_run_date(schedule=schedule)
    return result


def process_due_schedules() -> list[object]:
    """
    Process all ACTIVE schedules with ``next_run_date`` <= today.

    Single entry point used by the daily Celery beat task — corporate and
    subscription recurrence both flow through this function.
    """
    today = timezone.localdate()
    schedules = (
        RecurringSchedule.objects.select_related("content_type")
        .filter(status=RecurrenceStatus.ACTIVE, next_run_date__lte=today)
        .order_by("next_run_date")
    )
    results: list[object] = []
    for schedule in schedules:
        results.append(execute_recurrence(schedule=schedule))
    return results
