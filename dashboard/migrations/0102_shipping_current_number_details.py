# Generated by Django 4.2.5 on 2023-12-06 07:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0101_payment_gateway'),
    ]

    operations = [
        migrations.AddField(
            model_name='shipping',
            name='current_number_details',
            field=models.IntegerField(default=0),
        ),
    ]
