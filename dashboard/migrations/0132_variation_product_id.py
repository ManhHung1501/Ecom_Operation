# Generated by Django 4.2.5 on 2024-01-11 09:42

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0131_notification'),
    ]

    operations = [
        migrations.AddField(
            model_name='variation',
            name='product_id',
            field=models.CharField(max_length=255, null=True),
        ),
    ]
