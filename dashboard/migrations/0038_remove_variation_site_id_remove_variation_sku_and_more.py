# Generated by Django 4.2.5 on 2023-11-16 01:59

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0037_variation_sku'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='variation',
            name='site_id',
        ),
        migrations.RemoveField(
            model_name='variation',
            name='sku',
        ),
        migrations.DeleteModel(
            name='SKU',
        ),
        migrations.DeleteModel(
            name='Variation',
        ),
    ]
