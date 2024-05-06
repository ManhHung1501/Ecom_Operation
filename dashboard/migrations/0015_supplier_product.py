# Generated by Django 4.2.5 on 2023-11-13 10:13

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0014_site_status'),
    ]

    operations = [
        migrations.CreateModel(
            name='Supplier',
            fields=[
                ('supplier_id', models.AutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('email', models.EmailField(max_length=254, null=True)),
                ('phone', models.CharField(max_length=50, null=True)),
                ('address', models.CharField(max_length=255, null=True)),
                ('country', models.CharField(max_length=255, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='Product',
            fields=[
                ('product_id', models.AutoField(primary_key=True, serialize=False)),
                ('product_name', models.CharField(max_length=255, null=True)),
                ('date_created', models.DateTimeField()),
                ('date_modified', models.DateTimeField()),
                ('supplier', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dashboard.supplier')),
            ],
        ),
    ]
