# Generated by Django 4.2.5 on 2023-11-29 10:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0093_alter_shipping_detail_tracking_number'),
    ]

    operations = [
        migrations.AddField(
            model_name='order_line_item',
            name='tracking_number',
            field=models.ManyToManyField(to='dashboard.shipping'),
        ),
    ]