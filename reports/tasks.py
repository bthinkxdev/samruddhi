"""Celery tasks for the reports app."""

from __future__ import annotations

from celery import shared_task

from reports.services import ensure_daily_reports_current


@shared_task(name="reports.tasks.aggregate_daily_reports")
def aggregate_daily_reports_task() -> dict[str, int]:
    """
    Nightly beat task (00:10) to populate pre-aggregated report tables.
    Self-healing: back-fills any days missed while the worker was offline.
    """
    days = ensure_daily_reports_current()
    return {"days_aggregated": days}
