"""Domain exceptions for the orders app."""

from __future__ import annotations


class InvalidOrderStatusTransitionError(Exception):
    """Raised when an order status change is not allowed."""


class OrderNotEditableError(Exception):
    """Raised when an order-level edit (e.g. delivery address) isn't allowed in the order's current status."""
