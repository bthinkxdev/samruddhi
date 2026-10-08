"""Data layer for the reports app — pre-aggregated nightly report tables."""

from __future__ import annotations

from django.db import models

from core.models import TimeStampedModel


class DailySalesReport(TimeStampedModel):
    """Pre-aggregated daily sales metrics."""

    report_date = models.DateField(unique=True, db_index=True)
    order_count = models.PositiveIntegerField(default=0)
    revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    average_order_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    coupon_discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["-report_date"]
        verbose_name = "Daily sales report"
        verbose_name_plural = "Daily sales reports"


class DailyProductPerformance(TimeStampedModel):
    """Pre-aggregated per-product daily performance."""

    report_date = models.DateField(db_index=True)
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="daily_performance_reports",
    )
    units_sold = models.PositiveIntegerField(default=0)
    revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        unique_together = [("report_date", "product")]
        ordering = ["-report_date", "-revenue"]
        verbose_name = "Daily product performance"
        verbose_name_plural = "Daily product performance"


class DailyCustomerReport(TimeStampedModel):
    """Pre-aggregated daily customer metrics."""

    report_date = models.DateField(unique=True, db_index=True)
    new_customers = models.PositiveIntegerField(default=0)
    returning_customers = models.PositiveIntegerField(default=0)
    total_active_customers = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-report_date"]
        verbose_name = "Daily customer report"
        verbose_name_plural = "Daily customer reports"


class InventorySnapshot(TimeStampedModel):
    """Nightly inventory snapshot for low-stock alerting."""

    report_date = models.DateField(db_index=True)
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="inventory_snapshots",
    )
    stock_quantity = models.PositiveIntegerField()
    low_stock_threshold = models.PositiveIntegerField()
    is_low_stock = models.BooleanField(db_index=True)

    class Meta:
        unique_together = [("report_date", "product")]
        ordering = ["-report_date"]
        verbose_name = "Inventory snapshot"
        verbose_name_plural = "Inventory snapshots"
