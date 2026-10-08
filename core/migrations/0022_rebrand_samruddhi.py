from django.db import migrations

OLD_NAMES = {"Yarn Guy", "YARN GUY", "Yarnguy", "Floward"}


def rebrand_site_settings(apps, schema_editor):
    """Rename the stored brand and move previously hard-coded storefront copy into settings."""
    SiteSettings = apps.get_model("core", "SiteSettings")
    row = SiteSettings.objects.filter(pk=1).first()
    if row is None:
        return
    if row.site_name in OLD_NAMES:
        row.site_name = "Samruddhi"
    if not row.tagline:
        row.tagline = "Premium Gym Wear & Activewear"
    if not row.contact_phone:
        row.contact_phone = row.whatsapp_number
    if not row.address:
        row.address = (
            "Aluva - Perumbavoor KSRTC Road, valiyyaveettil building\n"
            "683105 Aluva KL\n"
            "India"
        )
    row.save()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0021_sitesettings_branding_fields"),
    ]

    operations = [
        migrations.RunPython(rebrand_site_settings, migrations.RunPython.noop),
    ]
