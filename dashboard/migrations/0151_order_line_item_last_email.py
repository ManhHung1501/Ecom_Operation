# Generated by Django 4.2.5 on 2024-01-31 10:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0150_site_auto_send_mail_site_email'),
    ]

    operations = [
        migrations.AddField(
            model_name='order_line_item',
            name='last_email',
            field=models.IntegerField(default=0),
        ),
    ]
