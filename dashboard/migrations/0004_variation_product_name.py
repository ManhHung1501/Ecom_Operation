# Generated by Django 4.2.5 on 2023-11-08 10:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0003_order_line_item_total_amount'),
    ]

    operations = [
        migrations.AddField(
            model_name='variation',
            name='product_name',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
