"""Domain exceptions for the marketing app."""

from __future__ import annotations


class MarketingError(Exception):
    """Base exception for marketing services."""


class InvalidCouponError(MarketingError):
    """Raised when a coupon code cannot be applied."""
