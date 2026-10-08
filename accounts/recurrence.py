"""Subscription recurrence handler registration."""

from __future__ import annotations

from accounts.models import Subscription
from accounts.subscription_services import execute_subscription_recurrence
from recurring.registry import register_recurrence_handler


def register() -> None:
    register_recurrence_handler(
        model_class=Subscription,
        handler=execute_subscription_recurrence,
    )


register()
