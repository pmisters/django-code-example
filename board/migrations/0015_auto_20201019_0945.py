# Generated by Django 3.1.2 on 2020-10-19 06:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('board', '0014_reservationroom_rate_plan_id_original'),
    ]

    operations = [
        migrations.AddField(
            model_name='reservationroom',
            name='policy',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='reservationroom',
            name='policy_original',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
