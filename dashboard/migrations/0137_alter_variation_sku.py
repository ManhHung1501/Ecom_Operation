# Generated by Django 4.2.5 on 2024-01-12 04:09

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0136_product_site'),
    ]

    operations = [
        migrations.AlterField(
            model_name='variation',
            name='sku',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='variations', to='dashboard.sku'),
        ),
    ]
