# Generated by Django 4.2.5 on 2023-11-24 04:09

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0080_order_refund_amount_order_line_item_fulfill_status_and_more'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Shipping',
        ),
    ]
