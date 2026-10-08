# Phase 8 — subscriptions, wishlist, gift calendar

from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_phase7_notification_preferences"),
        ("catalog", "0001_phase3_product_catalog"),
        ("recurring", "0001_phase8_recurring_engine"),
    ]

    operations = [
        migrations.CreateModel(
            name="Wishlist",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("session_key", models.CharField(blank=True, db_index=True, max_length=40, null=True)),
                ("share_token", models.CharField(blank=True, db_index=True, max_length=255)),
                (
                    "customer_profile",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="wishlists",
                        to="accounts.customerprofile",
                    ),
                ),
            ],
            options={"verbose_name": "Wishlist", "verbose_name_plural": "Wishlists"},
        ),
        migrations.CreateModel(
            name="Subscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("quantity", models.PositiveIntegerField(default=1)),
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
                    "customer_profile",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="subscriptions",
                        to="accounts.customerprofile",
                    ),
                ),
                (
                    "delivery_address",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="subscriptions",
                        to="accounts.address",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="subscriptions",
                        to="catalog.product",
                    ),
                ),
                (
                    "recurring_schedule",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="subscription",
                        to="recurring.recurringschedule",
                    ),
                ),
            ],
            options={"verbose_name": "Subscription", "verbose_name_plural": "Subscriptions"},
        ),
        migrations.CreateModel(
            name="GiftReminder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "occasion_type",
                    models.CharField(
                        choices=[
                            ("birthday", "Birthday"),
                            ("anniversary", "Anniversary"),
                            ("valentine", "Valentine's Day"),
                            ("mothers_day", "Mother's Day"),
                            ("fathers_day", "Father's Day"),
                            ("ramadan", "Ramadan"),
                            ("eid", "Eid"),
                            ("custom", "Custom"),
                        ],
                        max_length=20,
                    ),
                ),
                ("reminder_date", models.DateField(db_index=True)),
                ("recipient_name", models.CharField(max_length=120)),
                ("notes", models.TextField(blank=True)),
                ("notify_days_before", models.PositiveSmallIntegerField(default=7)),
                ("last_notified_on", models.DateField(blank=True, null=True)),
                (
                    "customer_profile",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="gift_reminders",
                        to="accounts.customerprofile",
                    ),
                ),
            ],
            options={
                "verbose_name": "Gift reminder",
                "verbose_name_plural": "Gift reminders",
                "ordering": ["reminder_date"],
            },
        ),
        migrations.CreateModel(
            name="WishlistItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="wishlist_items",
                        to="catalog.product",
                    ),
                ),
                (
                    "wishlist",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="accounts.wishlist",
                    ),
                ),
            ],
            options={"verbose_name": "Wishlist item", "verbose_name_plural": "Wishlist items"},
        ),
        migrations.AddConstraint(
            model_name="wishlist",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("customer_profile__isnull", False), ("session_key__isnull", True)),
                    models.Q(("customer_profile__isnull", True), ("session_key__isnull", False)),
                    _connector="OR",
                ),
                name="wishlist_owner_xor",
            ),
        ),
        migrations.AddConstraint(
            model_name="wishlistitem",
            constraint=models.UniqueConstraint(
                fields=("wishlist", "product"),
                name="wishlist_item_unique",
            ),
        ),
        migrations.AddIndex(
            model_name="subscription",
            index=models.Index(fields=["customer_profile", "status"], name="acct_sub_customer_idx"),
        ),
        migrations.AddIndex(
            model_name="giftreminder",
            index=models.Index(fields=["customer_profile", "reminder_date"], name="gift_rem_customer_idx"),
        ),
    ]
