# Phase 8 — shared recurring engine

from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RecurringSchedule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("object_id", models.PositiveBigIntegerField(db_index=True)),
                (
                    "frequency",
                    models.CharField(
                        choices=[("weekly", "Weekly"), ("monthly", "Monthly")],
                        max_length=20,
                    ),
                ),
                ("next_run_date", models.DateField(db_index=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("paused", "Paused"),
                            ("cancelled", "Cancelled"),
                        ],
                        db_index=True,
                        default="active",
                        max_length=20,
                    ),
                ),
                (
                    "content_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="recurring_schedules",
                        to="contenttypes.contenttype",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="recurring_schedules_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Recurring schedule",
                "verbose_name_plural": "Recurring schedules",
            },
        ),
        migrations.AddIndex(
            model_name="recurringschedule",
            index=models.Index(
                fields=["status", "next_run_date"],
                name="recurring_status_next_run_idx",
            ),
        ),
    ]
