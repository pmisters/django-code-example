from decimal import Decimal

from django.db import models
from django.db.models.fields.json import JSONField

from common.db import TimeableModel
from effective_tours.constants import Channels, ReservationSources, ReservationStatuses, RoomCloseReasons


class Reservation(TimeableModel):
    house = models.ForeignKey('houses.House', on_delete=models.PROTECT, related_name='+', blank=True, null=True)
    connection = models.ForeignKey(
        'channels.Connection', on_delete=models.PROTECT, related_name='+', blank=True, null=True
    )
    source = models.CharField(max_length=25, choices=ReservationSources.choices())
    channel = models.CharField(max_length=25, choices=Channels.choices(), blank=True, null=True)
    channel_id = models.CharField(max_length=20)
    status = models.CharField(
        max_length=25, choices=ReservationStatuses.choices(), default=ReservationStatuses.NEW.name
    )
    close_reason = models.CharField(max_length=25, choices=RoomCloseReasons.choices(), blank=True, null=True)

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

    room_count = models.PositiveSmallIntegerField(blank=True, default=1)
    currency = models.CharField(max_length=3, blank=True, null=True)
    tax = models.DecimalField(max_digits=10, decimal_places=2, blank=True, default=0)
    fees = models.DecimalField(max_digits=10, decimal_places=2, blank=True, default=0)
    guest_name = models.CharField(max_length=100, blank=True, default='')
    guest_surname = models.CharField(max_length=100, blank=True, default='')
    guest_email = models.CharField(max_length=200, blank=True, default='')
    guest_phone = models.CharField(max_length=50, blank=True, default='')
    guest_country = models.CharField(max_length=2, blank=True, default='')
    guest_nationality = models.CharField(max_length=50, blank=True, default='')
    guest_city = models.CharField(max_length=100, blank=True, default='')
    guest_address = models.CharField(max_length=250, blank=True, default='')
    guest_post_code = models.CharField(max_length=10, blank=True, default='')
    guest_comments = models.TextField(blank=True, default='')
    promo = models.CharField(max_length=250, blank=True, default='')
    creditcard_info = JSONField(blank=True, default=dict)
    payment_info = models.CharField(max_length=250, blank=True, default='')
    booked_at = models.DateTimeField()

    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(blank=True, null=True)

    # Odoo fields
    guest_contact_id = models.PositiveIntegerField(blank=True, null=True)
    guest_contact_ids = models.CharField(max_length=150, blank=True, default='')
    opportunity_id = models.PositiveIntegerField(blank=True, null=True)  # crm.lead
    quotation_id = models.PositiveIntegerField(blank=True, null=True)  # sale.order

    class Meta:
        app_label = 'board'
        indexes = [models.Index(fields=['channel_id'])]

    def __str__(self) -> str:
        return f"{self.source} CHANNEL ID={self.channel_id}"

    def save(self, **kwargs) -> None:
        for name in (
            'guest_name',
            'guest_surname',
            'guest_email',
            'guest_phone',
            'guest_country',
            'guest_nationality',
            'guest_city',
            'guest_address',
            'guest_post_code',
            'guest_comments',
            'guest_contact_ids',
            'promo',
            'payment_info',
        ):
            if getattr(self, name) is None:
                setattr(self, name, '')
        for name in ('price', 'price_accepted', 'tax', 'fees', 'netto_price', 'netto_price_accepted'):
            if getattr(self, name) is None:
                setattr(self, name, Decimal(0))

        if 'update_fields' in kwargs and kwargs['update_fields'] and 'updated_at' not in kwargs['update_fields']:
            kwargs['update_fields'].append('updated_at')
        super().save(**kwargs)
