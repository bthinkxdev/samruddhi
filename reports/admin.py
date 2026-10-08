"""Django admin registrations for the reports app."""

from __future__ import annotations

from django.contrib import admin

from reports.models import (
    DailyCustomerReport,
    DailyProductPerformance,
    DailySalesReport,
    InventorySnapshot,
)


@admin.register(DailySalesReport)
class DailySalesReportAdmin(admin.ModelAdmin):
    list_display = ("report_date", "order_count", "revenue", "average_order_value")
    ordering = ("-report_date",)
    date_hierarchy = "report_date"


@admin.register(DailyProductPerformance)
class DailyProductPerformanceAdmin(admin.ModelAdmin):
    list_display = ("report_date", "product", "units_sold", "revenue")
    list_filter = ("report_date",)
    ordering = ("-report_date", "-revenue")


@admin.register(DailyCustomerReport)
class DailyCustomerReportAdmin(admin.ModelAdmin):
    list_display = ("report_date", "new_customers", "returning_customers", "total_active_customers")
    ordering = ("-report_date",)


@admin.register(InventorySnapshot)
class InventorySnapshotAdmin(admin.ModelAdmin):
    list_display = ("report_date", "product", "stock_quantity", "is_low_stock")
    list_filter = ("report_date", "is_low_stock")
    ordering = ("-report_date",)
