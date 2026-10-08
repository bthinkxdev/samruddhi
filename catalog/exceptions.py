"""Catalog-specific exceptions raised by services."""

from __future__ import annotations


class CatalogError(Exception):
    """Base exception for the catalog app."""


class InsufficientStockError(CatalogError):
    """Raised when a stock adjustment would drive quantity below zero."""
