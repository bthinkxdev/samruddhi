"""Cross-app signal definitions for the accounts app."""

from __future__ import annotations

import django.dispatch

gift_reminder_due = django.dispatch.Signal()
