# Generated by Django 3.1 on 2020-09-16 06:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('board', '0004_auto_20200916_0915'),
    ]

    operations = [
        migrations.AddField(
            model_name='reservationroom',
            name='rate_id',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
