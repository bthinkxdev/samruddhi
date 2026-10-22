from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('whatsapp', '0001_initial'),
    ]

    operations = [
        # --- WhatsAppTemplate: Meta -> Gupshup field rename/removal ---
        migrations.RenameField(
            model_name='whatsapptemplate',
            old_name='template_name',
            new_name='template_id',
        ),
        migrations.AlterField(
            model_name='whatsapptemplate',
            name='template_id',
            field=models.CharField(
                help_text='Template UUID exactly as approved in the Gupshup dashboard.',
                max_length=512,
                verbose_name='Gupshup template ID',
            ),
        ),
        migrations.RemoveField(
            model_name='whatsapptemplate',
            name='language_code',
        ),
        # --- WhatsAppMessage: Meta -> Gupshup field rename/removal ---
        migrations.RenameField(
            model_name='whatsappmessage',
            old_name='template_name',
            new_name='template_id',
        ),
        migrations.RemoveField(
            model_name='whatsappmessage',
            name='language_code',
        ),
        migrations.RenameField(
            model_name='whatsappmessage',
            old_name='wamid',
            new_name='provider_message_id',
        ),
        migrations.AlterField(
            model_name='whatsappmessage',
            name='provider_message_id',
            field=models.CharField(
                blank=True,
                help_text="Gupshup's messageId, returned on submit and used to correlate webhook events.",
                max_length=255,
                null=True,
                unique=True,
                verbose_name='Gupshup message id',
            ),
        ),
    ]
