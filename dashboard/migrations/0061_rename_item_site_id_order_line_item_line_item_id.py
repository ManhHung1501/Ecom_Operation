# Generated by Django 4.2.5 on 2023-11-21 04:08

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0060_remove_order_line_item_line_item_id_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='order_line_item',
            old_name='item_site_id',
            new_name='line_item_id',
        ),
    ]
