"""Celery tasks for the shared recurring engine."""

from __future__ import annotations

from celery import shared_task

from recurring.services import process_due_schedules


@shared_task(name="recurring.tasks.process_due_schedules")
def process_due_schedules_task() -> int:
    """Daily beat task — processes corporate and subscription schedules together."""
    results = process_due_schedules()
    return len(results)
