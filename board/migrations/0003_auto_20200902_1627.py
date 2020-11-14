# Generated by Django 3.1 on 2020-09-02 13:27

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('board', '0002_auto_20200902_1440'),
    ]

    operations = [
        migrations.AddField(
            model_name='reservationroom',
            name='currency',
            field=models.CharField(blank=True, max_length=3, null=True),
        ),
        migrations.AddField(
            model_name='reservationroom',
            name='currency_changed',
            field=models.CharField(blank=True, max_length=3, null=True),
        ),
        migrations.AlterField(
            model_name='reservationday',
            name='reservation_room',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='day_prices', to='board.reservationroom'),
        ),
        migrations.AlterField(
            model_name='reservationroom',
            name='reservation',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rooms', to='board.reservation'),
        ),
    ]
