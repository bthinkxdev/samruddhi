from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_remove_giftreminder_customer_profile_and_more"),
    ]

    operations = [
        migrations.DeleteModel(
            name="Wholesaler",
        ),
    ]
