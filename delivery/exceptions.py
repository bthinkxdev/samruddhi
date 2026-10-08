"""Domain exceptions for the delivery app."""

from __future__ import annotations


class SlotFullyBookedError(Exception):
    """Raised when a delivery slot has no remaining capacity for a date."""
