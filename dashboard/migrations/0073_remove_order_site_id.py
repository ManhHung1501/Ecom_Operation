# Generated by Django 4.2.5 on 2023-11-22 10:14

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0072_alter_order_site_id'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='order',
            name='site_id',
        ),
    ]
