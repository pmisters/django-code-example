# Generated by Django 3.1 on 2020-09-02 11:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('board', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='reservationday',
            name='tax',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='reservationday',
            name='tax_changed',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]
