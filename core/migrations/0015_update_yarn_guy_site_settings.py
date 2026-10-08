from django.db import migrations


def update_yarn_guy_site_settings(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    SiteSettings.objects.filter(pk=1).update(
        site_name="Yarn Guy",
        whatsapp_number="+919961170396",
        vendor_email="yarnguyonline@gmail.com",
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0014_remove_contactinquiry_product_and_more"),
    ]

    operations = [
        migrations.RunPython(update_yarn_guy_site_settings, noop_reverse),
    ]
