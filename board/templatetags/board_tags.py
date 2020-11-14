import datetime
from typing import Any, Dict, List, Tuple

import inject
from django.template import Library
from django.utils import timezone

from board.permissions import Permissions
from board.value_objects import DAY_CELL_WIDTH
from cancelations.repositories import PoliciesRepo
from common.i18n import translate as _
from common.loggers import Logger
from effective_tours.constants import RoomCloseReasons
from geo.repositories import GeoRepo
from house_prices.entities import RatePlan
from house_prices.permissions import Permissions as PRICE_PERMISSIONS
from house_prices.repositories import PricesRepo
from house_prices.value_objects import RATES_MAX_OCCUPANCY
from houses.entities import House, RoomType
from houses.permissions import Permissions as HOUSE_PERMISSIONS
from houses.repositories import RoomTypesRepo, RoomsRepo
from members.entities import User

register = Library()


@register.simple_tag
def calendar_content_width(days: Dict[str, list]) -> str:
    if not days:
        return "0px"
    day_cnt = sum([len(x) for x in days.values()])
    return f"{day_cnt * DAY_CELL_WIDTH + 1}px"


@register.filter
def is_holiday(day: datetime.date) -> bool:
    return day.isoweekday() >= 6


@register.filter
def is_today(day: datetime.date) -> bool:
    return day == timezone.localdate()


@register.filter
def day_occupancy(occupancies: Dict[datetime.date, int], day: datetime.date) -> int:
    return occupancies.get(day) or 0


def reservation_shortcut_menu(context: Dict[str, Any]) -> Dict[str, Any]:
    user = context.get('user')
    if user is None or not user.is_authenticated:
        return {}
    house = context.get('CURRENT_HOUSE')
    if house is None:
        return {}
    permissions = [
        HOUSE_PERMISSIONS.HOUSE_READ,
        HOUSE_PERMISSIONS.ROOMTYPE_READ,
        HOUSE_PERMISSIONS.ROOM_READ,
        PRICE_PERMISSIONS.PLAN_READ,
        Permissions.RESERVATION_CREATE,
    ]
    if not all([user.check_perms(x, house_id=house.id) for x in permissions]):
        return {}
    room_types = select_room_types(house, user)
    rate_plans = select_rate_plans(house, user)
    return {
        'user': user,
        'house': house,
        'room_types': room_types,
        'rate_plans': rate_plans,
        'occupancies': [(x, f"{x} " + _('prices:page:ppl')) for x in range(1, RATES_MAX_OCCUPANCY)],
        'phone_codes': sorted(select_phone_codes(), key=lambda x: x[0]),
        'rooms': select_rooms(house, room_types),
        'close_reasons': RoomCloseReasons.choices(),
        'policies': select_policies(house, rate_plans),
    }


register.inclusion_tag('board/top.reservation_create.html', takes_context=True)(reservation_shortcut_menu)


@inject.autoparams('roomtypes_repo')
def select_room_types(house: 'House', user: 'User', roomtypes_repo: RoomTypesRepo) -> List[RoomType]:
    try:
        return roomtypes_repo.select(house, user=user)
    except Exception as err:
        Logger.warning(__name__, f"Error select Room Types for House ID={house.id} : {err}")
    return []


@inject.autoparams('prices_repo')
def select_rate_plans(house: 'House', user: 'User', prices_repo: PricesRepo) -> List[RatePlan]:
    try:
        return prices_repo.select_plans(house, user=user)
    except Exception as err:
        Logger.warning(__name__, f"Error select Rate Plans for House ID={house.id} : {err}")
    return []


@inject.autoparams('geo_repo')
def select_phone_codes(geo_repo: GeoRepo) -> List[Tuple[str, str]]:
    try:
        codes = geo_repo.get_phone_codes()
    except Exception as err:
        Logger.warning(__name__, f"Error select phone codes : {err}")
        return []
    if not codes:
        return []
    return list(set([(x, f"+{x}") for x in codes]))


@inject.autoparams('rooms_repo')
def select_rooms(house: 'House', room_types: List[RoomType], rooms_repo: RoomsRepo) -> List[Tuple[int, str]]:
    result = []
    try:
        _room_types = {x.id: x for x in room_types}
        data = rooms_repo.select(house_id=house.id)
    except Exception as err:
        Logger.warning(__name__, f"Error select Rooms for House ID={house.id} : {err}")
        return []
    for room in data:
        name = f"{room.name} / {_room_types[room.roomtype_id].name}" if room.roomtype_id in _room_types else room.name
        result.append((room.id, name))
    return sorted(result, key=lambda x: x[1])


@inject.autoparams('policies_repo')
def select_policies(house: 'House', rate_plans: List['RatePlan'], policies_repo: PoliciesRepo) -> Dict[int, str]:
    if not rate_plans:
        return {}
    try:
        policies = {x.id: x.name for x in policies_repo.select(house.id)}
    except Exception as err:
        Logger.warning(__name__, f"Error select Cancellation Policies for House ID={house.id} : {err}")
        return {}
    if not policies:
        return {}
    return {x.id: policies[x.policy_id] for x in rate_plans if x.policy_id in policies}
