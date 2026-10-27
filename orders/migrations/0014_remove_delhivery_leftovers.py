"""
Clean up after the removed Delhivery courier app.

Drops its leftover shipment table (if this database ever had it) and forgets its
migration records. Safe on fresh databases: everything is IF EXISTS / no-op.
Stale content types / permissions can be removed with
``python manage.py remove_stale_contenttypes``.
"""

from django.db import migrations


def drop_delhivery_leftovers(apps, schema_editor):
    connection = schema_editor.connection
    tables = connection.introspection.table_names()
    with connection.cursor() as cursor:
        if "delhivery_delhiveryshipment" in tables:
            cursor.execute("DROP TABLE delhivery_delhiveryshipment")
        cursor.execute("DELETE FROM django_migrations WHERE app = %s", ["delhivery"])


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0013_backfill_order_success_at"),
    ]

    operations = [
        migrations.RunPython(drop_delhivery_leftovers, migrations.RunPython.noop),
    ]
