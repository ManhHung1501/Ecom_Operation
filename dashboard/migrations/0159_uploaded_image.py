# Generated by Django 4.2.5 on 2024-04-11 09:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0158_remove_key_api_status_remove_key_api_type_api'),
    ]

    operations = [
        migrations.CreateModel(
            name='Uploaded_Image',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(upload_to='uploads/')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
