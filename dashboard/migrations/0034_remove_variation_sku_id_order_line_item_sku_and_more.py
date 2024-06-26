# Generated by Django 4.2.5 on 2023-11-16 01:50

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0033_rename_sku_variation_sku_id'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='variation',
            name='sku_id',
        ),
        migrations.AddField(
            model_name='order_line_item',
            name='sku',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='dashboard.sku'),
        ),
        migrations.AddField(
            model_name='variation',
            name='sku',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='dashboard.sku'),
        ),
    ]
