# Generated by Django 4.2.5 on 2023-12-05 10:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0097_alter_shipping_delivery_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='variation',
            name='variation_id',
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='shipping',
            name='order_number',
            field=models.CharField(max_length=100),
        ),
    ]
