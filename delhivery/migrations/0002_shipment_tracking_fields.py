from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delhivery", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="delhiveryshipment",
            name="pickup_location",
            field=models.CharField(
                blank=True,
                help_text="Delhivery pickup location name used for this shipment.",
                max_length=120,
                verbose_name="Pickup Location",
            ),
        ),
        migrations.AddField(
            model_name="delhiveryshipment",
            name="raw_create_response",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Full Delhivery API response from AWB creation.",
                verbose_name="Create Shipment Response",
            ),
        ),
        migrations.AddField(
            model_name="delhiveryshipment",
            name="last_status_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="Timestamp of the most recent webhook scan event applied.",
                verbose_name="Last Status At",
            ),
        ),
        migrations.AddField(
            model_name="delhiveryshipment",
            name="last_event_signature",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Dedup key for the most recently applied webhook event.",
                max_length=200,
                verbose_name="Last Event Signature",
            ),
        ),
    ]
