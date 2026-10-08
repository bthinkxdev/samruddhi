"""Cross-app signal definitions for the orders app."""

from __future__ import annotations

import django.dispatch

order_status_changed = django.dispatch.Signal()
