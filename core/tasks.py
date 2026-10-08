"""Celery tasks for core platform maintenance."""

from __future__ import annotations

from celery import shared_task
from django.core.cache import cache
from django.test import Client
from requests import RequestException


@shared_task(
    name="core.tasks.send_meta_purchase_event",
    bind=True,
    autoretry_for=(RequestException,),
    retry_backoff=30,
    retry_backoff_max=1800,
    max_retries=6,
)
def send_meta_purchase_event(self, *, order_id: int) -> bool:
    """Send a successful order to the Meta Conversions API (retried on transport errors)."""
    from core.meta_pixel import send_purchase_event

    return send_purchase_event(order_id=order_id)


@shared_task(name="core.tasks.refresh_sitemap_cache")
def refresh_sitemap_cache() -> int:
    """
    Warm sitemap endpoints nightly so the first crawler hit is fast.

    Returns HTTP status code from sitemap index request.
    """
    client = Client()
    response = client.get("/sitemap.xml")
    cache.set("seo:sitemap:last_refresh", response.status_code, timeout=86400 * 2)
    return response.status_code
