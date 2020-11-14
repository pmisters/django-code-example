from decimal import Decimal

from django.db import models
from django.db.models.fields.json import JSONField
from django.utils import timezone

from common.db import TimeableModel


class ReservationRoomQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_deleted=False)


class ReservationRoom(TimeableModel):
    reservation = models.ForeignKey('board.Reservation', on_delete=models.CASCADE, related_name='rooms')
    channel_id = models.CharField(max_length=20)
    rate_id = models.PositiveIntegerField(blank=True, null=True)

    rate_plan_id = models.PositiveIntegerField(blank=True, null=True)
    rate_plan_id_original = models.PositiveIntegerField(blank=True, null=True)

    channel_rate_id = models.CharField(max_length=20)
    channel_rate_id_changed = models.CharField(max_length=20)

    checkin = models.DateField()
    checkin_original = models.DateField()

    checkout = models.DateField()
    checkout_original = models.DateField()

    # original price from OTA
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, default=0)
    # price accepted by Hotelier
    price_accepted = models.DecimalField(max_digits=10, decimal_places=2, blank=True, default=0)

    # original price from OTA
    netto_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, default=0)
    # price accepted by Hotelier
    netto_price_accepted = models.DecimalField(max_digits=10, decimal_places=2, blank=True, default=0)

    external_id = models.CharField(max_length=20, blank=True, null=True)
    external_name = models.CharField(max_length=250, blank=True, default='')
    guest_name = models.CharField(max_length=150, blank=True, default='')
    guest_count = models.PositiveSmallIntegerField(blank=True, default=1)
    adults = models.PositiveSmallIntegerField(blank=True, default=0)
    children = models.PositiveSmallIntegerField(blank=True, default=0)
    max_children = models.PositiveSmallIntegerField(blank=True, default=0)
    extra_bed = models.PositiveSmallIntegerField(blank=True, default=0)
    with_breakfast = models.BooleanField(default=False)
    currency = models.CharField(max_length=3, blank=True, null=True)
    tax = models.DecimalField(max_digits=10, decimal_places=2, blank=True, default=0)
    fees = models.DecimalField(max_digits=10, decimal_places=2, blank=True, default=0)
    notes_extra = models.TextField(blank=True, default='')
    notes_facilities = models.TextField(blank=True, default='')
    notes_info = models.TextField(blank=True, default='')
    notes_meal = models.TextField(blank=True, default='')

    policy = JSONField(blank=True, default=dict)
    policy_original = JSONField(blank=True, default=dict)

    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    objects = ReservationRoomQuerySet.as_manager()

    class Meta:
        app_label = 'board'

    def __str__(self) -> str:
        return f"CHANNEL ID={self.channel_id} RATE={self.channel_rate_id}"

    def save(self, **kwargs) -> None:
        self.guest_count = self.guest_count or 1
        for name in ('adults', 'children', 'max_children', 'extra_bed'):
            if getattr(self, name) is None:
                setattr(self, name, 0)
        for name in ('price', 'price_accepted', 'tax', 'fees', 'netto_price', 'netto_price_accepted'):
            if getattr(self, name) is None:
                setattr(self, name, Decimal(0))
        for name in ('external_name', 'guest_name', 'notes_extra', 'notes_facilities', 'notes_info', 'notes_meal'):
            if getattr(self, name) is None:
                setattr(self, name, '')

        if 'update_fields' in kwargs and kwargs['update_fields']:
            kwargs['update_fields'].append('updated_at')
        super().save(**kwargs)

    def delete(self, **kwargs) -> None:
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at'])
