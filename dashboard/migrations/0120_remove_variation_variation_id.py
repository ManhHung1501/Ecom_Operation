# Generated by Django 4.2.5 on 2023-12-22 03:05

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0119_order_line_item_meta_data_id'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='variation',
            name='variation_id',
        ),
    ]
