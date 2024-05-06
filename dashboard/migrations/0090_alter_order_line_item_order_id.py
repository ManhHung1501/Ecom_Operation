# Generated by Django 4.2.5 on 2023-11-27 11:09

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0089_shipping_valid'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order_line_item',
            name='order_id',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='line_items', to='dashboard.order'),
        ),
    ]