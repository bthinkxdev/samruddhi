from django.db import migrations


def update_desert_star_site_settings(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    SiteSettings.objects.filter(pk=1).update(
        site_name="DESERT STAR MOBILE PHONES",
        whatsapp_number="971503131065",
        vendor_email="desertmobiles@gmail.com",
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0010_remove_sitesettings_logo_url_sitesettings_logo"),
    ]

    operations = [
        migrations.RunPython(update_desert_star_site_settings, noop_reverse),
    ]
