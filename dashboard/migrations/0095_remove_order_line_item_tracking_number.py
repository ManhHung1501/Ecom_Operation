# Generated by Django 4.2.5 on 2023-11-29 10:42

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0094_order_line_item_tracking_number'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='order_line_item',
            name='tracking_number',
        ),
    ]
