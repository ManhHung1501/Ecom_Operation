# Generated by Django 4.2.5 on 2023-11-20 09:54

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0056_batch_status_order_line_item_status'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='order_line_item',
            name='status',
        ),
    ]