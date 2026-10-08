from django.db import migrations


def update_desert_tech_colors(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    SiteSettings.objects.filter(pk=1).update(
        primary_color="#0369A1",
        secondary_color="#0B1220",
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0011_update_desert_star_site_settings"),
    ]

    operations = [
        migrations.RunPython(update_desert_tech_colors, noop_reverse),
    ]
