# Generated by Django 4.2.5 on 2023-11-16 01:58

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0036_remove_order_line_item_sku'),
    ]

    operations = [
        migrations.AddField(
            model_name='variation',
            name='sku',
            field=models.ForeignKey(blank=True, default='', on_delete=django.db.models.deletion.CASCADE, to='dashboard.sku'),
        ),
    ]
