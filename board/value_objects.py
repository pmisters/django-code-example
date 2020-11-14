import dataclasses
import datetime
import enum
import json
from decimal import Decimal
from typing import Dict, List, Optional, TYPE_CHECKING

from pydantic import BaseModel, Extra, Field

from common.mixins import DataContextMixin
from common.value_objects import TPrices
from events import Event

if TYPE_CHECKING:
    from board.entities import Reservation, ReservationRoom
    from cancelations.entities import Policy
    from house_prices.entities import Rate, RatePlan
    from houses.entities import House, Room, RoomType, RoomTypeDetails

DAY_CELL_WIDTH = 36
MAX_OCCUPANCY_PERIOD = 730  # days

#
# Contexts
#


@dataclasses.dataclass
class CalendarContext(DataContextMixin):
    house: "House"
    base_date: datetime.date
    start_date: datetime.date
    end_date: datetime.date
    dates: Dict[int, List[datetime.date]] = dataclasses.field(default_factory=dict)
    room_types: List["RoomTypeDetails"] = dataclasses.field(default_factory=list)
    rooms: List["Room"] = dataclasses.field(default_factory=list)
    occupancies: Dict[int, Dict[datetime.date, Optional[int]]] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class OccupanciesContext(DataContextMixin):
    start_date: datetime.date
    end_date: datetime.date
    occupancies: Dict[int, Dict[datetime.date, Optional[int]]] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class ReservationUpdateContext(DataContextMixin):
    start_date: datetime.date
    end_date: datetime.date
    reservation: "Reservation"


@dataclasses.dataclass
class ReservationCalcContext(DataContextMixin):
    house: 'House'
    room_type: 'RoomType'
    rate_plan: 'RatePlan'
    rates: List['Rate'] = dataclasses.field(default_factory=list)
    rate: 'Rate' = None
    prices: TPrices = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class ReservationDetailsContext(DataContextMixin):
    house: "House"
    reservation: "Reservation"
    payed_amount: Decimal


@dataclasses.dataclass
class ReservationVerifyContext(DataContextMixin):
    house: 'House'
    reservation: 'Reservation'


@dataclasses.dataclass
class ReservationPricesUpdateContext(DataContextMixin):
    house: 'House'
    reservation: 'Reservation'
    reservation_room: 'ReservationRoom'
    rate_plans: List['RatePlan'] = dataclasses.field(default_factory=list)
    room_types: List['RoomType'] = dataclasses.field(default_factory=list)
    rooms: List['Room'] = dataclasses.field(default_factory=list)
    policies: List['Policy'] = dataclasses.field(default_factory=list)


#
# Errors
#


class CalendarErrors(enum.Enum):
    error = enum.auto()
    missed_house = enum.auto()


class OccupancyErrors(enum.Enum):
    error = enum.auto()
    missed_house = enum.auto()
    missed_roomtype = enum.auto()
    missed_user = enum.auto()
    wrong_period = enum.auto()


class ReservationErrors(enum.Enum):
    busy_room = enum.auto()
    error = enum.auto()
    missed_guest = enum.auto()
    missed_house = enum.auto()
    missed_rate = enum.auto()
    missed_rateplan = enum.auto()
    missed_reservation = enum.auto()
    missed_room = enum.auto()
    missed_roomtype = enum.auto()
    missed_user = enum.auto()
    room_close_reservation = enum.auto()
    save = enum.auto()
    wrong_period = enum.auto()


#
# Events
#


class ReservationCreateEvent(Event):
    name = "board::reservation::create"


class ReservationUpdateEvent(Event):
    name = "board::reservation::update"


class ReservationCancelEvent(Event):
    name = "board::reservation::cancel"


#
# Schemas
#


class CachedReservationTag(BaseModel):
    code: str
    name: str

    class Config:
        extra = Extra.ignore


class CachedReservation(BaseModel):
    pk: str
    reservation_id: int
    grid: str
    grid_id: int
    checkin: datetime.datetime
    checkout: datetime.datetime
    daystart: int = None
    dayend: int = None
    channel_id: str = None
    source: str = None
    source_code: str = None
    status: str = None
    adults: int = None
    children: int = None
    meal: str = None
    name: str = None
    phone: str = None
    money_room: str = None
    money_extra: str = None
    total: str = None
    payed: str = None
    balance: str = None
    has_balance: bool = True
    split_left: bool = False
    split_right: bool = False
    close_reason: str = None
    close_reason_name: str = None
    comments: str = None
    tags: List[CachedReservationTag] = Field(default_factory=list)

    class Config:
        extra = Extra.ignore


def reservation_request_dumps(data, default=None, **kwargs):
    data['prices'] = {k.isoformat(): v for k, v in data['prices'].items()}
    return json.dumps(data, default=default, **kwargs)


class ReservationRequest(BaseModel):
    roomtype_id: int
    plan_id: int
    checkin: datetime.date
    checkout: datetime.date
    guests: int
    guest_name: str = ''
    guest_surname: str = ''
    guest_email: str = ''
    guest_phone: str = ''
    notes: str = ''
    rate_id: int = None
    prices: TPrices = Field(default_factory=dict)

    class Config:
        extra = Extra.ignore
        json_dumps = reservation_request_dumps
