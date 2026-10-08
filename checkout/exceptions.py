"""Domain exceptions for the checkout app."""

from __future__ import annotations


class CheckoutError(Exception):
    """Base exception for checkout services."""


class CheckoutSessionError(CheckoutError):
    """Raised when checkout session state is invalid for placement."""


class IdempotentOrderExistsError(CheckoutError):
    """Raised when an order already exists for the idempotency key — carries order."""

    def __init__(self, order) -> None:
        self.order = order
        super().__init__("Order already exists for idempotency key.")
