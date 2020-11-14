# Generated by Django 3.1 on 2020-09-16 06:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('board', '0003_auto_20200902_1627'),
    ]

    operations = [
        migrations.RenameField(
            model_name='reservationroom',
            old_name='rate_id',
            new_name='channel_rate_id',
        ),
        migrations.RenameField(
            model_name='reservationroom',
            old_name='rate_id_changed',
            new_name='channel_rate_id_changed',
        ),
        migrations.AddField(
            model_name='reservationroom',
            name='rate_plan_id',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='reservation',
            name='source',
            field=models.CharField(choices=[('AGODA', 'Agoda.com'), ('BOOKING', 'Booking.com'), ('EXPEDIA', 'Expedia.com'), ('MANUAL', 'Manual')], max_length=25),
        ),
    ]