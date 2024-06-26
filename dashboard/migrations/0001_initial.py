# Generated by Django 4.2.5 on 2023-11-07 10:14

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Site',
            fields=[
                ('site_id', models.CharField(max_length=8, primary_key=True, serialize=False)),
                ('link', models.URLField(unique=True)),
                ('name', models.CharField(max_length=50, null=True)),
                ('platform', models.CharField(max_length=255)),
                ('authentication', models.JSONField(max_length=255)),
            ],
        ),
        migrations.CreateModel(
            name='SKU',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sku', models.CharField(max_length=50)),
                ('product_id', models.CharField(max_length=255)),
                ('attributes', models.JSONField()),
                ('quantity', models.IntegerField(default=0)),
                ('cost', models.FloatField(default=0)),
                ('child_sku', models.CharField(max_length=50, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='Variation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('product_id', models.CharField(max_length=255)),
                ('attributes', models.JSONField()),
                ('sku', models.CharField(max_length=50)),
                ('created_by', models.CharField(max_length=50)),
                ('date_created', models.DateTimeField()),
                ('date_modified', models.DateTimeField()),
                ('site_id', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dashboard.site', verbose_name='site')),
            ],
        ),
        migrations.CreateModel(
            name='Order',
            fields=[
                ('order_id', models.AutoField(primary_key=True, serialize=False)),
                ('order_number', models.CharField(max_length=200)),
                ('transaction_id', models.CharField(max_length=100, null=True)),
                ('status', models.CharField(choices=[('Pending', 'PENDING'), ('On-Hold', 'ON-HOLD'), ('Failed', 'FAILED'), ('Processing', 'PROCESSING'), ('Fulfilling', 'FULFILLING'), ('Cancelled', 'CANCELLED'), ('Completed', 'COMPLETED'), ('Refunded', 'REFUNDED')], default='Pending', max_length=50)),
                ('first_name', models.CharField(max_length=255, null=True)),
                ('last_name', models.CharField(max_length=255, null=True)),
                ('email', models.EmailField(max_length=254, null=True)),
                ('phone', models.CharField(max_length=50, null=True)),
                ('address_1', models.CharField(max_length=255, null=True)),
                ('address_2', models.CharField(max_length=255, null=True)),
                ('city', models.CharField(max_length=255, null=True)),
                ('state_code', models.CharField(max_length=255, null=True)),
                ('postcode', models.CharField(max_length=255, null=True)),
                ('country_code', models.CharField(max_length=10, null=True)),
                ('currency', models.CharField(max_length=5)),
                ('payment_method', models.CharField(max_length=255, null=True)),
                ('payment_method_title', models.CharField(max_length=255, null=True)),
                ('discount_amount', models.FloatField(default=0)),
                ('shipping_amount', models.FloatField(default=0)),
                ('total_amount', models.FloatField(default=0)),
                ('date_paid', models.DateTimeField()),
                ('date_created', models.DateTimeField()),
                ('date_modified', models.DateTimeField()),
                ('date_completed', models.DateTimeField()),
                ('site_id', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dashboard.site', verbose_name='site')),
            ],
        ),
    ]
