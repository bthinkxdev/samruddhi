"""Replace the leftover gym-wear default tagline with jewellery copy.

The tagline is the homepage <title>/meta description, the footer tagline and the
PLP fallback description. Only the untouched old default is replaced, so a tagline
the client already edited in Dashboard > Settings is never overwritten.
"""

from django.db import migrations

OLD_TAGLINE = "Premium Gym Wear & Activewear"
NEW_TAGLINE = "Traditional & Contemporary Jewellery"


def forwards(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    SiteSettings.objects.filter(tagline=OLD_TAGLINE).update(tagline=NEW_TAGLINE)


def backwards(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    SiteSettings.objects.filter(tagline=NEW_TAGLINE).update(tagline=OLD_TAGLINE)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0023_sitesettings_whatsapp_otp_template_id"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
