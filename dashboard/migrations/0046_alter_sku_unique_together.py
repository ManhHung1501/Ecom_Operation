# Generated by Django 4.2.5 on 2023-11-16 04:09

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0045_sku_attributes_id_alter_variation_attributes_id'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='sku',
            unique_together={('product_id', 'attributes_id')},
        ),
    ]
