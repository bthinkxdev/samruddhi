"""Celery tasks for the WhatsApp app."""

from __future__ import annotations

import logging

from celery import shared_task

from whatsapp.exceptions import WhatsAppRetryableError
from whatsapp.services import deliver_message, mark_message_failed

logger = logging.getLogger(__name__)

MAX_RETRIES = 5


@shared_task(bind=True, name="whatsapp.tasks.send_message", max_retries=MAX_RETRIES)
def send_message_task(self, *, message_id: int) -> None:
    """
    Deliver one queued WhatsApp message. Retries transient failures (network, 5xx,
    rate limits) with exponential backoff: 1, 2, 4, 8, 16 minutes.
    """
    try:
        deliver_message(message_id)
    except WhatsAppRetryableError as exc:
        if self.request.retries >= self.max_retries:
            logger.error("WhatsApp message %s failed after retries: %s", message_id, exc)
            mark_message_failed(message_id, exc)
            return
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))
