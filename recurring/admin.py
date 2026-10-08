"""Django admin registrations for the recurring app."""

from __future__ import annotations

from django.contrib import admin

from recurring.models import RecurringSchedule


@admin.register(RecurringSchedule)
class RecurringScheduleAdmin(admin.ModelAdmin):
    list_display = ("id", "content_type", "object_id", "frequency", "next_run_date", "status")
    list_filter = ("status", "frequency")
