import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import attr

from effective_tours.constants import (
    Channels,
    DEFAULT_CHECKIN_TIME,
    DEFAULT_CHECKOUT_TIME,
    META_COMPARABLE,
    META_LABEL,
    ReservationSources,
    ReservationStatuses,
    RoomCloseReasons,
)
from house_prices.entities import RatePlan
from houses.entities import Room, RoomType

if TYPE_CHECKING:
    from channels.entities import Connection
    from channels.ota.schemas import OtaReservation, OtaReservationPrice, OtaReservationRoom


@attr.s
class ReservationDay:
    id: Optional[int] = attr.ib(validator=attr.validators.optional(attr.validators.instance_of(int)))
    reservation_room_id: Optional[int] = attr.ib(validator=attr.validators.optional(attr.validators.instance_of(int)))
    day: datetime.date = attr.ib(validator=attr.validators.instance_of(datetime.date))
    roomtype_id: Optional[int] = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(int))
    )
    room_id: Optional[int] = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(int))
    )

    price_changed: Decimal = attr.ib(default=Decimal(0), validator=attr.validators.instance_of(Decimal))
    price_accepted: Decimal = attr.ib(default=Decimal(0), validator=attr.validators.instance_of(Decimal))
    tax: Decimal = attr.ib(default=Decimal(0), validator=attr.validators.instance_of(Decimal))
    currency: Optional[str] = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(str))
    )

    # Temporary storages for working data
    room_type: Optional[RoomType] = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(RoomType))
    )
    room: Optional[Room] = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(Room))
    )

    # Read-Only fields
    price_original: Decimal = attr.ib(default=Decimal(0), validator=attr.validators.instance_of(Decimal))

    @staticmethod
    def load(room_id: Optional[int], data: 'OtaReservationPrice'):
        return ReservationDay(
            id=None,
            reservation_room_id=room_id,
            day=data.day,
            price_changed=data.price,
            tax=data.tax,
            currency=data.currency,
            roomtype_id=data.roomtype_id,
        )

    def update(self, data: 'OtaReservationPrice') -> bool:
        is_changed = False
        if self.price_changed != data.price:
            self.price_changed = data.price
            is_changed = True
        mapping = {'day': 'day', 'tax': 'tax', 'currency': 'currency'}
        for field, source in mapping.items():
            value = getattr(data, source)
            if getattr(self, field) != value:
                setattr(self, field, value)
        return is_changed


@attr.s
class ReservationRoom:
    id: Optional[int] = attr.ib(validator=attr.validators.optional(attr.validators.instance_of(int)))
    reservation_id: Optional[int] = attr.ib(validator=attr.validators.optional(attr.validators.instance_of(int)))
    channel_id: str = attr.ib(validator=attr.validators.instance_of(str))
    channel_rate_id: str = attr.ib(validator=attr.validators.instance_of(str))
    checkin: datetime.date = attr.ib(validator=attr.validators.instance_of(datetime.date))
    checkout: datetime.date = attr.ib(validator=attr.validators.instance_of(datetime.date))

    rate_plan_id: Optional[int] = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(int))
    )
    rate_id: Optional[int] = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(int))
    )
    external_id: Optional[str] = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(str))
    )
    external_name: str = attr.ib(default='', validator=attr.validators.instance_of(str))
    guest_name: str = attr.ib(default='', validator=attr.validators.instance_of(str))
    guest_count: int = attr.ib(default=1, validator=attr.validators.instance_of(int))
    adults: int = attr.ib(default=0, validator=attr.validators.instance_of(int))
    children: int = attr.ib(default=0, validator=attr.validators.instance_of(int))
    max_children: int = attr.ib(default=0, validator=attr.validators.instance_of(int))
    extra_bed: int = attr.ib(default=0, validator=attr.validators.instance_of(int))
    with_breakfast: bool = attr.ib(default=False, validator=attr.validators.instance_of(bool))
    currency: Optional[str] = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(str))
    )
    policy: Dict[str, Any] = attr.ib(default=attr.Factory(dict), validator=attr.validators.instance_of(dict))

    # original price from OTA
    price: Decimal = attr.ib(default=Decimal(0), validator=attr.validators.instance_of(Decimal))
    # price accepted by Hotelier
    price_accepted: Decimal = attr.ib(default=Decimal(0), validator=attr.validators.instance_of(Decimal))

    # original price from OTA
    netto_price: Decimal = attr.ib(default=Decimal(0), validator=attr.validators.instance_of(Decimal))
    # price accepted by Hotelier
    netto_price_accepted: Decimal = attr.ib(default=Decimal(0), validator=attr.validators.instance_of(Decimal))

    tax: Decimal = attr.ib(default=Decimal(0), validator=attr.validators.instance_of(Decimal))
    fees: Decimal = attr.ib(default=Decimal(0), validator=attr.validators.instance_of(Decimal))
    notes_extra: str = attr.ib(default='', validator=attr.validators.instance_of(str))
    notes_facilities: str = attr.ib(default='', validator=attr.validators.instance_of(str))
    notes_info: str = attr.ib(default='', validator=attr.validators.instance_of(str))
    notes_meal: str = attr.ib(default='', validator=attr.validators.instance_of(str))

    day_prices: List[ReservationDay] = attr.ib(
        default=attr.Factory(list),
        validator=attr.validators.deep_iterable(
            member_validator=attr.validators.instance_of(ReservationDay),
            iterable_validator=attr.validators.instance_of(list),
        ),
    )

    # Read-Only
    checkin_original: Optional[datetime.date] = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(datetime.date))
    )
    checkout_original: Optional[datetime.date] = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(datetime.date))
    )
    rate_plan_id_original: Optional[int] = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(int))
    )
    policy_original: Optional[Dict[str, Any]] = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(dict))
    )
    is_deleted: bool = attr.ib(default=False, validator=attr.validators.instance_of(bool))
    deleted_at: Optional[datetime.datetime] = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(datetime.datetime))
    )

    # Temporary storages for working data
    rate_plan: Optional['RatePlan'] = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(RatePlan))
    )
    rate_plan_original: Optional['RatePlan'] = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(RatePlan))
    )

    def get_nights(self) -> int:
        return (self.checkout - self.checkin).days

    @staticmethod
    def load(reservation_id: Optional[int], data: 'OtaReservationRoom'):
        result = ReservationRoom(
            id=None,
            reservation_id=reservation_id,
            channel_id=data.channel_id,
            channel_rate_id=data.channel_rate_id,
            rate_plan_id=data.rate_plan_id,
            policy=data.policy,
            checkin=data.checkin,
            checkout=data.checkout,
            external_id=data.external_id,
            external_name=data.external_name,
            guest_name=data.guest_name,
            guest_count=data.guest_count,
            adults=data.adults,
            children=data.children,
            max_children=data.max_children,
            extra_bed=data.extra_bed,
            with_breakfast=data.with_breakfast,
            currency=data.currency,
            price=data.price,
            netto_price=data.netto_price,
            tax=data.tax,
            fees=data.fees,
            notes_extra=data.notes_extra,
            notes_facilities=data.notes_facilities,
            notes_info=data.notes_info,
            notes_meal=data.notes_meal,
        )
        if data.day_prices:
            for price in data.day_prices:
                result.day_prices.append(ReservationDay.load(result.id, price))
        return result

    def update(self, data: 'OtaReservationRoom') -> bool:
        is_changed = False
        if self.checkin != data.checkin:
            self.checkin = data.checkin
            is_changed = True
        if self.checkout != data.checkout:
            self.checkout = data.checkout
            is_changed = True
        if self.channel_rate_id != data.channel_rate_id:
            self.channel_rate_id = data.channel_rate_id
            is_changed = True
        mapping = {
            'channel_id': 'channel_id',
            'rate_plan_id': 'rate_plan_id',
            'policy': 'policy',
            'external_name': 'external_name',
            'guest_name': 'guest_name',
            'guest_count': 'guest_count',
            'adults': 'adults',
            'children': 'children',
            'max_children': 'max_children',
            'extra_bed': 'extra_bed',
            'with_breakfast': 'with_breakfast',
            'currency': 'currency',
            'price': 'price',
            'tax': 'tax',
            'fees': 'fees',
            'netto_price': 'netto_price',
            'notes_extra': 'notes_extra',
            'notes_facilities': 'notes_facilities',
            'notes_info': 'notes_info',
            'notes_meal': 'notes_meal',
        }
        for field, source in mapping.items():
            value = getattr(data, source)
            if getattr(self, field) != value:
                setattr(self, field, value)

        existed_prices = {x.day: x for x in self.day_prices}
        prices = []
        for price_data in data.day_prices:
            if price_data.day in existed_prices:
                price = attr.evolve(existed_prices[price_data.day])
                is_price_changed = price.update(price_data)
            else:
                price = ReservationDay.load(self.id, price_data)
                is_price_changed = True
            prices.append(price)
            is_changed = is_changed or is_price_changed
        self.day_prices = prices

        return is_changed


@attr.s
class Reservation:
    id: Optional[int] = attr.ib(validator=attr.validators.optional(attr.validators.instance_of(int)))
    house_id: int = attr.ib(validator=attr.validators.instance_of(int))
    connection_id: Optional[int] = attr.ib(validator=attr.validators.optional(attr.validators.instance_of(int)))
    source: ReservationSources = attr.ib(validator=attr.validators.instance_of(ReservationSources))
    channel: Optional[Channels] = attr.ib(validator=attr.validators.optional(attr.validators.instance_of(Channels)))
    channel_id: str = attr.ib(validator=attr.validators.instance_of(str))
    checkin: datetime.date = attr.ib(
        validator=attr.validators.instance_of(datetime.date), metadata={META_LABEL: 'CheckIn', META_COMPARABLE: True}
    )
    checkout: datetime.date = attr.ib(
        validator=attr.validators.instance_of(datetime.date), metadata={META_LABEL: 'CheckOut', META_COMPARABLE: True}
    )
    booked_at: datetime.datetime = attr.ib(validator=attr.validators.instance_of(datetime.datetime))
    status: ReservationStatuses = attr.ib(
        default=ReservationStatuses.NEW,
        validator=attr.validators.instance_of(ReservationStatuses),
        metadata={META_LABEL: 'Status', META_COMPARABLE: True},
    )
    close_reason: Optional[RoomCloseReasons] = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(RoomCloseReasons))
    )
    room_count: int = attr.ib(default=1, validator=attr.validators.instance_of(int))
    currency: Optional[str] = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(str))
    )

    # original price from OTA
    price: Decimal = attr.ib(default=Decimal(0), validator=attr.validators.instance_of(Decimal))
    # price accepted by Hotelier
    price_accepted: Decimal = attr.ib(default=Decimal(0), validator=attr.validators.instance_of(Decimal))

    # original price from OTA
    netto_price: Decimal = attr.ib(default=Decimal(0), validator=attr.validators.instance_of(Decimal))
    # price accepted by Hotelier
    netto_price_accepted: Decimal = attr.ib(default=Decimal(0), validator=attr.validators.instance_of(Decimal))

    tax: Decimal = attr.ib(default=Decimal(0), validator=attr.validators.instance_of(Decimal))
    fees: Decimal = attr.ib(default=Decimal(0), validator=attr.validators.instance_of(Decimal))

    guest_name: str = attr.ib(default='', validator=attr.validators.instance_of(str))
    guest_surname: str = attr.ib(default='', validator=attr.validators.instance_of(str))
    guest_email: str = attr.ib(default='', validator=attr.validators.instance_of(str))
    guest_phone: str = attr.ib(default='', validator=attr.validators.instance_of(str))
    guest_country: str = attr.ib(default='', validator=attr.validators.instance_of(str))
    guest_nationality: str = attr.ib(default='', validator=attr.validators.instance_of(str))
    guest_city: str = attr.ib(default='', validator=attr.validators.instance_of(str))
    guest_address: str = attr.ib(default='', validator=attr.validators.instance_of(str))
    guest_post_code: str = attr.ib(default='', validator=attr.validators.instance_of(str))
    guest_comments: str = attr.ib(default='', validator=attr.validators.instance_of(str))
    guest_contact_id: Optional[int] = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(int))
    )
    guest_contact_ids: List[int] = attr.ib(
        default=attr.Factory(list),
        validator=attr.validators.deep_iterable(
            member_validator=attr.validators.instance_of(int), iterable_validator=attr.validators.instance_of(list)
        ),
    )

    promo: str = attr.ib(default='', validator=attr.validators.instance_of(str))
    payment_info: str = attr.ib(default='', validator=attr.validators.instance_of(str))
    creditcard_info: Dict[str, Any] = attr.ib(default=attr.Factory(dict), validator=attr.validators.instance_of(dict))

    is_verified: bool = attr.ib(
        default=False,
        validator=attr.validators.instance_of(bool),
        metadata={META_LABEL: 'Verified', META_COMPARABLE: True},
    )
    verified_at: Optional[datetime.datetime] = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(datetime.datetime))
    )

    # Odoo Fields
    opportunity_id: Optional[int] = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(int))
    )
    quotation_id: Optional[int] = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(int))
    )

    rooms: List[ReservationRoom] = attr.ib(
        default=attr.Factory(list),
        validator=attr.validators.deep_iterable(
            member_validator=attr.validators.instance_of(ReservationRoom),
            iterable_validator=attr.validators.instance_of(list),
        ),
    )

    class Meta:
        name = 'Reservation'

    def allow_delete(self) -> bool:
        return self.source == ReservationSources.MANUAL

    def allow_update_prices(self) -> bool:
        return self.status not in (ReservationStatuses.CANCEL, ReservationStatuses.CLOSE)

    def get_checkin_time(self) -> datetime.datetime:
        return datetime.datetime.combine(self.checkin, datetime.time(DEFAULT_CHECKIN_TIME))

    def get_checkout_time(self) -> datetime.datetime:
        return datetime.datetime.combine(self.checkout, datetime.time(DEFAULT_CHECKOUT_TIME))

    def get_guest_name(self) -> str:
        return ' '.join([self.guest_name, self.guest_surname]).strip()

    def get_id(self) -> str:
        if self.channel_id != '':
            return self.channel_id
        return f"ET{self.id}"

    def get_id_for_log(self) -> str:
        return f"{self.get_id()} {self.checkin.strftime('%d/%m/%Y')}..{self.checkout.strftime('%d/%m/%Y')}"

    def get_nights(self) -> int:
        return (self.checkout - self.checkin).days

    def get_opportunity_name(self) -> str:
        return f"{self.checkin.strftime('%d.%b')}-{self.checkout.strftime('%d.%b')}, {self.get_guest_name()}"

    def get_total_adults(self) -> int:
        if not self.rooms:
            return 0
        return sum([x.adults or 0 for x in self.rooms])

    def get_total_children(self) -> int:
        if not self.rooms:
            return 0
        return sum([x.children or 0 for x in self.rooms])

    def is_ota(self) -> bool:
        return self.source != ReservationSources.MANUAL

    @staticmethod
    def load(connection: 'Connection', data: 'OtaReservation'):
        result = Reservation(
            id=None,
            house_id=connection.house_id,
            connection_id=connection.id,
            source=ReservationSources.get_by_name(connection.channel.name),
            channel=connection.channel,
            channel_id=data.channel_id,
            checkin=data.checkin,
            checkout=data.checkout,
            booked_at=data.booking_date,
            status=data.status,
            room_count=data.room_count,
            currency=data.currency,
            price=data.price,
            netto_price=data.netto_price,
            tax=data.tax,
            fees=data.fees,
            promo=data.promo,
            payment_info=data.payment_info,
        )
        if data.guest is not None:
            result.guest_name = data.guest.name
            result.guest_surname = data.guest.surname
            result.guest_email = data.guest.email
            result.guest_phone = data.guest.phone
            result.guest_country = data.guest.country
            result.guest_city = data.guest.city
            result.guest_nationality = data.guest.nationality
            result.guest_address = data.guest.address
            result.guest_comments = data.guest.comments
            result.guest_post_code = data.guest.post_code
        if data.creditcard_info is not None:
            # Update only not empty values
            creditcard_info = {k: v for k, v in data.creditcard_info.dict().items() if v != ''}
            result.creditcard_info.update(creditcard_info)
        if data.rooms:
            for room in data.rooms:
                result.rooms.append(ReservationRoom.load(result.id, room))
        return result

    def update(self, data: 'OtaReservation') -> bool:
        is_changed = False
        if self.checkin != data.checkin:
            self.checkin = data.checkin
            is_changed = True
        if self.checkout != data.checkout:
            self.checkout = data.checkout
            is_changed = True

        mapping = {
            'booked_at': 'booking_date',
            'status': 'status',
            'room_count': 'room_count',
            'currency': 'currency',
            'price': 'price',
            'tax': 'tax',
            'fees': 'fees',
            'netto_price': 'netto_price',
            'promo': 'promo',
            'payment_info': 'payment_info',
        }
        for field, source in mapping.items():
            value = getattr(data, source)
            if getattr(self, field) != value:
                setattr(self, field, value)

        guest_mapping = {
            'guest_name': 'name',
            'guest_surname': 'surname',
            'guest_email': 'email',
            'guest_phone': 'phone',
            'guest_country': 'country',
            'guest_city': 'city',
            'guest_nationality': 'nationality',
            'guest_address': 'address',
            'guest_comments': 'comments',
            'guest_post_code': 'post_code',
        }
        for field, source in guest_mapping.items():
            value = getattr(data.guest, source) if data.guest is not None else ''
            if getattr(self, field) != value:
                setattr(self, field, value)

        if data.creditcard_info is not None:
            value = data.creditcard_info.dict()
            if self.creditcard_info != value:
                self.creditcard_info = value
        elif self.creditcard_info:
            self.creditcard_info = {}

        existed_rooms = {x.external_id: x for x in self.rooms}
        rooms = []
        for room_data in data.rooms:
            if room_data.external_id in existed_rooms:
                room = attr.evolve(existed_rooms[room_data.external_id])
                is_room_changed = room.update(room_data)
            else:
                room = ReservationRoom.load(self.id, room_data)
                is_room_changed = True
            rooms.append(room)
            is_changed = is_changed or is_room_changed
        self.rooms = rooms

        return is_changed
