# Generated by Django 4.2.5 on 2023-11-21 10:43

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0067_sku'),
    ]

    operations = [
        migrations.AddField(
            model_name='order_line_item',
            name='sku',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='dashboard.sku', to_field='sku'),
        ),
    ]