# Generated by Django 4.2.5 on 2023-11-15 11:03

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0027_alter_order_order_id'),
    ]

    operations = [
        migrations.AlterField(
            model_name='variation',
            name='sku',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='dashboard.sku'),
        ),
    ]
