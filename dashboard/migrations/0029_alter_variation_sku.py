# Generated by Django 4.2.5 on 2023-11-16 01:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0028_alter_variation_sku'),
    ]

    operations = [
        migrations.AlterField(
            model_name='variation',
            name='sku',
            field=models.CharField(max_length=50),
        ),
    ]
