# Generated by Django 4.2.5 on 2024-02-01 10:03

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0152_remove_order_line_item_last_email_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='email_sent',
            old_name='email_emplate',
            new_name='email_template',
        ),
    ]
