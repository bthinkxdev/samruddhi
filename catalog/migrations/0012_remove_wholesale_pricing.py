from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0011_alter_productvariant_variant_type"),
    ]

    operations = [
        migrations.DeleteModel(
            name="ProductWholesaleTier",
        ),
        migrations.RemoveField(
            model_name="product",
            name="wholesale_rate",
        ),
    ]
