# Generated by Django 4.2.5 on 2023-12-19 07:44

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0113_alter_batch_date_created'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='order',
            name='fulfill_status',
        ),
    ]
