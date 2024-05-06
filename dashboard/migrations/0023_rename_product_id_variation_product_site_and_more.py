# Generated by Django 4.2.5 on 2023-11-14 03:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0022_remove_product_site_id_alter_product_site_link'),
    ]

    operations = [
        migrations.RenameField(
            model_name='variation',
            old_name='product_id',
            new_name='product_site',
        ),
        migrations.RemoveField(
            model_name='variation',
            name='created_by',
        ),
        migrations.RemoveField(
            model_name='variation',
            name='date_created',
        ),
        migrations.RemoveField(
            model_name='variation',
            name='product_name',
        ),
        migrations.AlterField(
            model_name='variation',
            name='attributes_id',
            field=models.CharField(default='NA', max_length=500),
        ),
    ]
