# Generated by Django 4.2.5 on 2023-11-29 08:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0091_alter_shipping_detail_tracking_detail'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='coupon_code',
            field=models.JSONField(null=True),
        ),
    ]