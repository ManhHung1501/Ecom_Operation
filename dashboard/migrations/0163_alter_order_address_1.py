# Generated by Django 4.2.5 on 2024-04-23 10:17

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0162_email_sent_automail'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='address_1',
            field=models.TextField(null=True),
        ),
    ]
