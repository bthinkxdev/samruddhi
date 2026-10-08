"""Write operations and business rules for the delivery app."""

from __future__ import annotations

from datetime import date

from django.db import IntegrityError, transaction
