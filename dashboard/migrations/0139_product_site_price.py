# Generated by Django 4.2.5 on 2024-01-18 03:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0138_alter_order_line_item_sku_alter_site_platform_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='product_site',
            name='price',
            field=models.FloatField(default=0),
        ),
    ]