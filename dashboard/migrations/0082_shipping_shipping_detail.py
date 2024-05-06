# Generated by Django 4.2.5 on 2023-11-24 04:55

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0081_remove_shipping_date_modified_remove_shipping_id_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Shipping',
            fields=[
                ('tracking_number', models.CharField(max_length=255, primary_key=True, serialize=False)),
                ('order_number', models.CharField(max_length=100, null=True)),
                ('courier_code', models.CharField(max_length=100, null=True)),
                ('created_at', models.DateTimeField(null=True)),
                ('update_date', models.DateTimeField(null=True)),
                ('shipping_date', models.DateTimeField(null=True)),
                ('archived', models.IntegerField(default=0)),
                ('delivery_status', models.CharField(max_length=50, null=True)),
                ('updating', models.IntegerField(default=0)),
                ('destination', models.CharField(max_length=10, null=True)),
                ('original', models.CharField(max_length=10, null=True)),
                ('weight', models.CharField(max_length=100, null=True)),
                ('substatus', models.CharField(max_length=50, null=True)),
                ('status_info', models.CharField(max_length=50, null=True)),
                ('previously', models.CharField(max_length=50, null=True)),
                ('destination_track_number', models.CharField(max_length=100, null=True)),
                ('exchange_number', models.CharField(max_length=100, null=True)),
                ('consignee', models.CharField(max_length=100, null=True)),
                ('scheduled_delivery_date', models.DateTimeField(null=True)),
                ('scheduled_address', models.CharField(max_length=255, null=True)),
                ('lastest_checkpoint_time', models.DateTimeField(null=True)),
                ('transit_time', models.IntegerField(null=True)),
                ('stay_time', models.IntegerField(null=True)),
                ('origin_info', models.JSONField(null=True)),
                ('destination_info', models.JSONField(null=True)),
                ('upload_to_site', models.IntegerField(default=0)),
                ('upload_to_payment_gateway', models.IntegerField(default=0)),
                ('line_item_id', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dashboard.order_line_item')),
            ],
        ),
        migrations.CreateModel(
            name='Shipping_Detail',
            fields=[
                ('shipping_detail_id', models.AutoField(primary_key=True, serialize=False)),
                ('checkpoint_date', models.DateTimeField()),
                ('tracking_detail', models.CharField(max_length=255, null=True)),
                ('location', models.CharField(max_length=255, null=True)),
                ('checkpoint_delivery_status', models.CharField(max_length=50, null=True)),
                ('checkpoint_delivery_substatus', models.CharField(max_length=50, null=True)),
                ('origin_destination', models.IntegerField(default=0)),
                ('mail_to', models.CharField(max_length=255, null=True)),
                ('data_sent', models.TextField(null=True)),
                ('tracking_number', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dashboard.shipping')),
            ],
        ),
    ]
