"""Strategy registry mapping content types to recurrence executors."""

from __future__ import annotations

from typing import Callable

from django.contrib.contenttypes.models import ContentType

RecurrenceHandler = Callable[..., object]

RECURRENCE_HANDLERS: dict[str, RecurrenceHandler] = {}


def register_recurrence_handler(*, model_class: type, handler: RecurrenceHandler) -> None:
    """Register a handler for a domain model class."""
    RECURRENCE_HANDLERS[model_class._meta.model_name] = handler


def get_recurrence_handler(*, content_type: ContentType) -> RecurrenceHandler:
    """Return the handler for a content type or raise KeyError."""
    handler = RECURRENCE_HANDLERS.get(content_type.model)
    if handler is None:
        raise KeyError(f"No recurrence handler registered for {content_type.model}")
    return handler
