# Generated by Django 4.2.5 on 2023-11-15 01:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0025_remove_site_webhook_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='variation',
            name='product_site_name',
            field=models.CharField(max_length=255, null=True),
        ),
    ]
