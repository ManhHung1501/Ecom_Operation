# Generated by Django 4.2.5 on 2023-11-09 08:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0006_variation_attributes_id'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='date_completed',
            field=models.DateTimeField(null=True),
        ),
        migrations.AlterField(
            model_name='order',
            name='date_paid',
            field=models.DateTimeField(null=True),
        ),
    ]