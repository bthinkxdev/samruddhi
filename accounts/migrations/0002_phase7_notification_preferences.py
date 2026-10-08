# Generated manually for Phase 7 notification preferences.

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_phase2_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="customerprofile",
            name="notify_via_email",
            field=models.BooleanField(
                default=True,
                help_text="Receive order updates via email.",
                verbose_name="Email notifications",
            ),
        ),
        migrations.AddField(
            model_name="customerprofile",
            name="notify_via_sms",
            field=models.BooleanField(
                default=True,
                help_text="Receive order updates via SMS.",
                verbose_name="SMS notifications",
            ),
        ),
        migrations.AddField(
            model_name="customerprofile",
            name="notify_via_whatsapp",
            field=models.BooleanField(
                default=False,
                help_text="Receive order updates via WhatsApp.",
                verbose_name="WhatsApp notifications",
            ),
        ),
    ]
