# Generated by Django 4.2.5 on 2024-01-04 10:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0125_alter_template_export_name'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='order_line_item',
            name='supplier',
        ),
        migrations.AddField(
            model_name='template_export',
            name='object_export',
            field=models.CharField(max_length=255, null=True),
        ),
    ]
