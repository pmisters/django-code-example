# Generated by Django 3.1 on 2020-09-23 08:44

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('board', '0009_auto_20200923_1050'),
    ]

    operations = [
        migrations.RenameField(
            model_name='reservation',
            old_name='checkin_changed',
            new_name='checkin_original',
        ),
        migrations.RenameField(
            model_name='reservation',
            old_name='checkout_changed',
            new_name='checkout_original',
        ),
        migrations.RenameField(
            model_name='reservationroom',
            old_name='checkin_changed',
            new_name='checkin_original',
        ),
        migrations.RenameField(
            model_name='reservationroom',
            old_name='checkout_changed',
            new_name='checkout_original',
        ),
    ]
