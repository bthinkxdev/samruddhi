"""Create Django auth Groups for SuperAdmin, StoreAdmin, and CorporateManager."""

from __future__ import annotations

from django.db import migrations

ROLE_NAMES: tuple[str, ...] = ("SuperAdmin", "StoreAdmin", "CorporateManager")

STORE_ADMIN_APPS: tuple[str, ...] = (
    "catalog",
    "orders",
    "marketing",
    "cms",
    "cart",
    "checkout",
    "delivery",
)

CORPORATE_MANAGER_APPS: tuple[str, ...] = ("corporate", "orders")


def create_role_groups(apps, schema_editor) -> None:
    """Provision the three platform role groups with scaffolded permissions."""
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    all_permissions = list(Permission.objects.all())
    store_permissions = list(
        Permission.objects.filter(content_type__app_label__in=STORE_ADMIN_APPS)
    )
    corporate_permissions = list(
        Permission.objects.filter(content_type__app_label__in=CORPORATE_MANAGER_APPS)
    )

    role_permissions = {
        "SuperAdmin": all_permissions,
        "StoreAdmin": store_permissions,
        "CorporateManager": corporate_permissions,
    }

    for role_name in ROLE_NAMES:
        group, _ = Group.objects.get_or_create(name=role_name)
        group.permissions.set(role_permissions[role_name])


def remove_role_groups(apps, schema_editor) -> None:
    """Remove scaffolded role groups on migration rollback."""
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=ROLE_NAMES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial_currency_model"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_role_groups, remove_role_groups),
    ]
