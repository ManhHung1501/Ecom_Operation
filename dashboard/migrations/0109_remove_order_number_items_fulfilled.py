# Generated by Django 4.2.5 on 2023-12-08 10:04

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0108_order_line_item_price'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='order',
            name='number_items_fulfilled',
        ),
    ]
