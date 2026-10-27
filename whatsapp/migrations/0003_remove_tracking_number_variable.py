from django.db import migrations, models


class Migration(migrations.Migration):
    """Courier tracking number removed from the WhatsApp template variables."""

    dependencies = [
        ("whatsapp", "0002_gupshup_migration"),
    ]

    operations = [
        migrations.AlterField(
            model_name="whatsapptemplate",
            name="body_variables",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Ordered list filling {{1}}, {{2}}, ... e.g. ["customer_name", "order_number", "store_name"]. Allowed: customer_name, order_number, store_name, order_total, order_status, order_items',
                verbose_name="Body variables",
            ),
        ),
    ]
