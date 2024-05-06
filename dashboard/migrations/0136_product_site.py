# Generated by Django 4.2.5 on 2024-01-11 10:57

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0135_delete_product_site'),
    ]

    operations = [
        migrations.CreateModel(
            name='Product_Site',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('product_id', models.CharField(max_length=255, null=True)),
                ('product_site_id', models.CharField(max_length=255)),
                ('product_site_name', models.CharField(max_length=255, null=True)),
                ('link', models.URLField(null=True)),
                ('date_created', models.DateTimeField(null=True)),
                ('date_modified', models.DateTimeField(null=True)),
                ('site_id', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dashboard.site')),
            ],
            options={
                'unique_together': {('site_id', 'product_site_id')},
            },
        ),
    ]