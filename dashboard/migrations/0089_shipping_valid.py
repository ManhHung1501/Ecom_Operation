# Generated by Django 4.2.5 on 2023-11-27 09:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0088_rename_fulfill_status_order_line_item_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='shipping',
            name='valid',
            field=models.IntegerField(default=1),
        ),
    ]
