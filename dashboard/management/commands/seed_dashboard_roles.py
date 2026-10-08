"""Create the dashboard RBAC groups and optionally assign a user to one.

Usage:
    python manage.py seed_dashboard_roles
    python manage.py seed_dashboard_roles --user admin --role SuperAdmin
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from dashboard.access import DASHBOARD_GROUPS

User = get_user_model()


class Command(BaseCommand):
    help = "Create dashboard staff groups (SuperAdmin, StoreAdmin) and optionally assign a user."

    def add_arguments(self, parser):
        parser.add_argument("--user", help="Username to add to a dashboard group.")
        parser.add_argument(
            "--role",
            choices=list(DASHBOARD_GROUPS),
            default="SuperAdmin",
            help="Group to assign the given user to (default: SuperAdmin).",
        )

    def handle(self, *args, **options):
        for name in DASHBOARD_GROUPS:
            group, created = Group.objects.get_or_create(name=name)
            status = "created" if created else "already exists"
            self.stdout.write(f"Group '{name}' {status}.")

        username = options.get("user")
        if username:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist as exc:
                raise CommandError(f"User '{username}' not found.") from exc
            group = Group.objects.get(name=options["role"])
            user.groups.add(group)
            self.stdout.write(
                self.style.SUCCESS(f"Added '{username}' to group '{options['role']}'.")
            )

        self.stdout.write(self.style.SUCCESS("Dashboard roles seeded."))
