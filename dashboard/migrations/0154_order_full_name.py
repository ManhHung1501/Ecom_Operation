# Generated by Django 4.2.5 on 2024-03-05 10:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0153_rename_email_emplate_email_sent_email_template'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='full_name',
            field=models.CharField(max_length=255, null=True),
        ),
    ]
