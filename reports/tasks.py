"""Celery tasks for the reports app."""

from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from reports.models import DailySalesReport
from reports.services import aggregate_daily_reports


@shared_task(name="reports.tasks.aggregate_daily_reports")
def aggregate_daily_reports_task() -> dict[str, int]:
    """
    Nightly beat task to populate pre-aggregated report tables.
    Includes self-healing logic to backfill missing days if the worker was offline.
    """
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    
    last_report = DailySalesReport.objects.order_by("-report_date").first()
    
    if last_report:
        start_date = last_report.report_date + timedelta(days=1)
        #cap the backfill to a maximum of 60 days to prevent overloading the worker
        if (yesterday - start_date).days > 60:
            start_date = yesterday - timedelta(days=60)
    else:
        start_date = yesterday
        
    #always ensure we at least run for yesterday, even if reports are up to date
    #(this ensures any late-night straggler orders are fully captured)
    if start_date > yesterday:
        start_date = yesterday

    current = start_date
    latest_result = {}
    
    while current <= yesterday:
        latest_result = aggregate_daily_reports(report_date=current)
        current += timedelta(days=1)
        
    return latest_result
