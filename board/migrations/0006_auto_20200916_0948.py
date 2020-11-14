# Generated by Django 3.1 on 2020-09-16 06:48

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('channels', '0004_rateplanmapping_child_rates'),
        ('board', '0005_reservationroom_rate_id'),
    ]

    operations = [
        migrations.AlterField(
            model_name='reservation',
            name='connection',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='channels.connection'),
        ),
    ]
