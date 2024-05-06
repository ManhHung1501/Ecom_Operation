# Generated by Django 4.2.5 on 2023-12-08 03:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0106_alter_batch_date_modified'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['date_created'], name='dashboard_o_date_cr_7f8bc7_idx'),
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['status'], name='dashboard_o_status_2e9809_idx'),
        ),
        migrations.AddIndex(
            model_name='shipping',
            index=models.Index(fields=['created_at'], name='dashboard_s_created_7d1791_idx'),
        ),
        migrations.AddIndex(
            model_name='shipping',
            index=models.Index(fields=['update_date'], name='dashboard_s_update__4d61cd_idx'),
        ),
        migrations.AddIndex(
            model_name='shipping',
            index=models.Index(fields=['delivery_status'], name='dashboard_s_deliver_4b983e_idx'),
        ),
    ]