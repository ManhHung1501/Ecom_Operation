# Generated by Django 4.2.5 on 2023-11-21 10:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0066_remove_order_line_item_sku_alter_variation_sku_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='SKU',
            fields=[
                ('_id', models.AutoField(primary_key=True, serialize=False)),
                ('sku', models.CharField(max_length=255, unique=True)),
                ('product_id', models.CharField(max_length=255, null=True)),
                ('attributes_id', models.CharField(max_length=255)),
                ('attributes', models.JSONField()),
                ('quantity', models.IntegerField(default=0)),
                ('cost', models.FloatField(default=0)),
                ('child_sku', models.CharField(max_length=50, null=True)),
            ],
            options={
                'unique_together': {('product_id', 'attributes_id')},
            },
        ),
    ]
