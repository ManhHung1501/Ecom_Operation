# Generated by Django 4.2.5 on 2023-11-29 10:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0095_remove_order_line_item_tracking_number'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shipping',
            name='line_item_id',
            field=models.ManyToManyField(related_name='shippings', to='dashboard.order_line_item'),
        ),
    ]
