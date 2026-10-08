from django.db import migrations


def darken_desert_tech_accent(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    SiteSettings.objects.filter(pk=1).update(
        primary_color="#0369A1",
        secondary_color="#0B1220",
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0012_desert_tech_site_colors"),
    ]

    operations = [
        migrations.RunPython(darken_desert_tech_accent, noop_reverse),
    ]
