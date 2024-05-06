# Generated by Django 4.2.5 on 2023-11-24 01:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0078_order_payment_status'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='shipping',
            name='address_1',
        ),
        migrations.RemoveField(
            model_name='shipping',
            name='address_2',
        ),
        migrations.RemoveField(
            model_name='shipping',
            name='city',
        ),
        migrations.RemoveField(
            model_name='shipping',
            name='country_code',
        ),
        migrations.RemoveField(
            model_name='shipping',
            name='first_name',
        ),
        migrations.RemoveField(
            model_name='shipping',
            name='last_name',
        ),
        migrations.RemoveField(
            model_name='shipping',
            name='phone',
        ),
        migrations.RemoveField(
            model_name='shipping',
            name='postcode',
        ),
        migrations.RemoveField(
            model_name='shipping',
            name='state_code',
        ),
        migrations.AddField(
            model_name='order',
            name='shipping_address_1',
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='shipping_address_2',
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='shipping_city',
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='shipping_country_code',
            field=models.CharField(max_length=10, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='shipping_first_name',
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='shipping_last_name',
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='shipping_phone',
            field=models.CharField(max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='shipping_postcode',
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='shipping_state_code',
            field=models.CharField(max_length=255, null=True),
        ),
    ]
