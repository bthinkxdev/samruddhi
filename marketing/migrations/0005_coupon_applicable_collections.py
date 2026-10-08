from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0026_collections"),
        ("marketing", "0004_delete_giftcard"),
    ]

    operations = [
        migrations.RenameField(
            model_name="coupon",
            old_name="applicable_categories",
            new_name="applicable_collections",
        ),
        migrations.AlterField(
            model_name="coupon",
            name="applicable_collections",
            field=models.ManyToManyField(
                blank=True,
                related_name="coupons",
                to="catalog.collection",
                verbose_name="Applicable collections",
            ),
        ),
    ]
