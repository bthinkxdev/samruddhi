from django.db import migrations, models


class Migration(migrations.Migration):
    """Additive only: two blank-by-default text columns, no existing data touched."""

    dependencies = [
        ("core", "0019_sitesettings_order_notification_email"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="meta_pixel_id",
            field=models.CharField(
                blank=True,
                help_text="Numeric Pixel / Dataset ID from Meta Events Manager. Leave blank to disable tracking (falls back to the META_PIXEL_ID env var).",
                max_length=32,
                verbose_name="Meta Pixel ID",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="meta_capi_access_token",
            field=models.CharField(
                blank=True,
                help_text="Enables server-side Purchase events. Falls back to the META_CAPI_ACCESS_TOKEN env var.",
                max_length=512,
                verbose_name="Meta Conversions API access token",
            ),
        ),
    ]
