# Generated by Django 3.1 on 2020-09-25 05:57

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('board', '0011_reservation_close_reason'),
    ]

    operations = [
        migrations.RenameField(
            model_name='reservationday',
            old_name='room_type_id',
            new_name='roomtype_id',
        ),
    ]
