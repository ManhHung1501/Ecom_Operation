# Generated by Django 4.2.5 on 2023-11-07 11:02

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Batch',
            fields=[
                ('batch_id', models.AutoField(primary_key=True, serialize=False)),
                ('supplier', models.CharField(blank=True, max_length=255, null=True)),
                ('date_created', models.DateTimeField()),
                ('date_modified', models.DateTimeField()),
                ('created_by', models.CharField(blank=True, max_length=255, null=True)),
            ],
        ),
        migrations.RemoveField(
            model_name='sku',
            name='id',
        ),
        migrations.AlterField(
            model_name='sku',
            name='sku',
            field=models.CharField(max_length=50, primary_key=True, serialize=False),
        ),
        migrations.CreateModel(
            name='Order_Line_Item',
            fields=[
                ('line_item_id', models.AutoField(primary_key=True, serialize=False)),
                ('item_name', models.CharField(blank=True, max_length=255, null=True)),
                ('quantity', models.IntegerField(default=1)),
                ('subtotal_amount', models.FloatField(default=0)),
                ('date_modified', models.DateTimeField()),
                ('supplier', models.CharField(blank=True, max_length=255, null=True)),
                ('batch_id', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='dashboard.batch')),
                ('order_id', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dashboard.order')),
                ('sku', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='dashboard.sku')),
            ],
        ),
    ]
