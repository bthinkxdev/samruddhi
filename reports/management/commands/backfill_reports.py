"""
Recompute pre-aggregated daily reports for a historical date range.

Needed after any change to what aggregate_daily_reports() counts (e.g. which order
statuses count as revenue) — the nightly Celery beat task only fills gaps (days with
no stored row at all); it never re-aggregates a date that already has one. This
command force-recomputes every day in range regardless of whether a row exists.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.core.management.base import BaseCommand, CommandParser
from django.utils import timezone

from orders.models import Order
from reports.services import aggregate_daily_reports


class Command(BaseCommand):
    help = (
        "Recompute DailySalesReport / DailyCustomerReport / DailyProductPerformance / "
        "InventorySnapshot for every day in a date range, overwriting any existing rows."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--start", type=str, default=None,
            help="YYYY-MM-DD (default: the date of the earliest order)",
        )
        parser.add_argument(
            "--end", type=str, default=None,
            help="YYYY-MM-DD (default: yesterday)",
        )

    def handle(self, *args, **options) -> None:
        end = (
            datetime.strptime(options["end"], "%Y-%m-%d").date()
            if options["end"]
            else timezone.localdate() - timedelta(days=1)
        )
        if options["start"]:
            start = datetime.strptime(options["start"], "%Y-%m-%d").date()
        else:
            first_order = Order.objects.order_by("created_at").first()
            if first_order is None:
                self.stdout.write(self.style.WARNING("No orders exist; nothing to backfill."))
                return
            start = timezone.localtime(first_order.created_at).date()

        if start > end:
            self.stdout.write(self.style.WARNING(f"start ({start}) is after end ({end}); nothing to do."))
            return

        current = start
        days = 0
        while current <= end:
            aggregate_daily_reports(report_date=current)
            days += 1
            current += timedelta(days=1)

        self.stdout.write(self.style.SUCCESS(f"Recomputed reports for {days} day(s): {start} to {end}."))
