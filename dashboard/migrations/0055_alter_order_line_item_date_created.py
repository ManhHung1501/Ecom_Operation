# Generated by Django 4.2.5 on 2023-11-17 11:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0054_order_line_item_date_created'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order_line_item',
            name='date_created',
            field=models.DateTimeField(),
        ),
    ]
