from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0018_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="order_notification_email",
            field=models.EmailField(
                blank=True,
                help_text="Email address to notify whenever a new order is placed. Leave blank to disable.",
                max_length=254,
                verbose_name="Order Notification Email",
            ),
        ),
    ]
