# Generated by Django 4.2.5 on 2023-11-13 10:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0016_product_site'),
    ]

    operations = [
        migrations.AddField(
            model_name='product_site',
            name='product_site_name',
            field=models.CharField(max_length=255, null=True),
        ),
    ]
