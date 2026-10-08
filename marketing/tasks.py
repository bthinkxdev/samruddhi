"""Celery tasks for the marketing app."""

from __future__ import annotations

from celery import shared_task

from marketing.services_abandoned import scan_abandoned_carts


@shared_task(name="marketing.tasks.scan_abandoned_carts")
def scan_abandoned_carts_task() -> int:
    """Beat task: email customers with abandoned carts."""
    return scan_abandoned_carts()
