# Generated by Django 4.2.5 on 2023-11-16 01:55

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0035_remove_variation_sku'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='order_line_item',
            name='sku',
        ),
    ]
