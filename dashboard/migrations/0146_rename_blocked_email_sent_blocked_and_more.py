# Generated by Django 4.2.5 on 2024-01-25 02:05

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0145_email_sent'),
    ]

    operations = [
        migrations.RenameField(
            model_name='email_sent',
            old_name='Blocked',
            new_name='blocked',
        ),
        migrations.RenameField(
            model_name='email_sent',
            old_name='Bounce',
            new_name='bounce',
        ),
        migrations.RenameField(
            model_name='email_sent',
            old_name='Click',
            new_name='click',
        ),
        migrations.RenameField(
            model_name='email_sent',
            old_name='Deferred',
            new_name='deferred',
        ),
        migrations.RenameField(
            model_name='email_sent',
            old_name='Delivered',
            new_name='delivered',
        ),
        migrations.RenameField(
            model_name='email_sent',
            old_name='Dropped',
            new_name='dropped',
        ),
        migrations.RenameField(
            model_name='email_sent',
            old_name='Open',
            new_name='open_event',
        ),
        migrations.RenameField(
            model_name='email_sent',
            old_name='Processed',
            new_name='processed',
        ),
    ]
