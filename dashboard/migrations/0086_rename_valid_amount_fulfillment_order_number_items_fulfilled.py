# Generated by Django 4.2.5 on 2023-11-27 07:59

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0085_order_valid_amount_fulfillment'),
    ]

    operations = [
        migrations.RenameField(
            model_name='order',
            old_name='valid_amount_fulfillment',
            new_name='number_items_fulfilled',
        ),
    ]