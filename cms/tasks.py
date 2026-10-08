"""Celery tasks for the cms app."""

from __future__ import annotations

from celery import shared_task

from cms.services import refresh_homepage_cache


@shared_task(name="cms.tasks.refresh_homepage_cache")
def refresh_homepage_cache_task() -> int:
    """Rebuild the Redis homepage sections snapshot."""
    return refresh_homepage_cache()
