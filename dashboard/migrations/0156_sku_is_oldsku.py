# Generated by Django 4.2.5 on 2024-03-06 03:42

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0155_remove_order_full_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='sku',
            name='is_oldsku',
            field=models.IntegerField(default=0),
        ),
    ]