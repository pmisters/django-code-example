import dataclasses
import datetime
from typing import Dict, List, TYPE_CHECKING

import inject
from dateutil import relativedelta
from django.utils import timezone
from returns.maybe import Nothing
from returns.pipeline import flow
from returns.pointfree import bind_result
from returns.result import Success

from board.repositories import OccupancyRepo, ReservationsRepo
from board.value_objects import MAX_OCCUPANCY_PERIOD, OccupancyErrors
from common import functions as cf
from common.value_objects import ResultE, ServiceBase
from houses.repositories import HousesRepo, RoomTypesRepo, RoomsRepo
from members.repositories import MembersRepo

if TYPE_CHECKING:
    from houses.entities import House, RoomType
    from members.entities import User


@dataclasses.dataclass
class Context:
    house_id: int = None
    roomtype_id: int = None
    start_date: datetime.date = None
    end_date: datetime.date = None
    houses: List['House'] = dataclasses.field(default_factory=list)
    users: Dict[int, 'User'] = dataclasses.field(default_factory=dict)
    room_types: Dict[int, List['RoomType']] = dataclasses.field(default_factory=dict)
    room_count: Dict[int, Dict[int, int]] = dataclasses.field(default_factory=dict)
    busy_days: Dict[int, Dict[int, Dict[datetime.date, int]]] = dataclasses.field(default_factory=dict)
    occupancies: Dict[int, Dict[int, Dict[datetime.date, int]]] = dataclasses.field(default_factory=dict)


class CalculateOccupancy(ServiceBase):
    @inject.autoparams()
    def __init__(
        self,
        houses_repo: HousesRepo,
        members_repo: MembersRepo,
        roomtypes_repo: RoomTypesRepo,
        rooms_repo: RoomsRepo,
        reservations_repo: ReservationsRepo,
        occupancy_repo: OccupancyRepo,
    ):
        self._houses_repo = houses_repo
        self._members_repo = members_repo
        self._roomtypes_repo = roomtypes_repo
        self._rooms_repo = rooms_repo
        self._reservations_repo = reservations_repo
        self._occupancy_repo = occupancy_repo

    def execute(
        self,
        house_id: int = None,
        roomtype_id: int = None,
        start_date: datetime.date = None,
        end_date: datetime.date = None,
    ) -> ResultE[None]:
        ctx = Context(house_id=house_id, roomtype_id=roomtype_id, start_date=start_date, end_date=end_date)

        return flow(
            ctx,
            self.get_calendar_period,
            bind_result(self.select_houses),
            bind_result(self.select_company_bots),
            bind_result(self.select_roomtypes),
            bind_result(self.populate_roomtypes),
            bind_result(self.select_busy_days),
            bind_result(self.calculate_occupancy),
            bind_result(self.save),
            bind_result(lambda x: Success(None))
        )

    def _select_all_roomtypes(self, ctx: Context) -> ResultE[Context]:
        for house in ctx.houses:
            try:
                if house.id not in ctx.room_types:
                    ctx.room_types[house.id] = []
                ctx.room_types[house.id] += self._roomtypes_repo.select(house, user=ctx.users.get(house.company.id))
            except Exception as err:
                return self._error(
                    f"Error select Room Types for House ID={house.id}", ctx, OccupancyErrors.error, exc=err,
                )
        return Success(ctx)

    def _select_specific_roomtype(self, ctx: Context) -> ResultE[Context]:
        pk = cf.get_int_or_none(ctx.roomtype_id) or 0
        if pk <= 0:
            return self._error(f"Wrong Room Type ID={pk}", ctx, OccupancyErrors.missed_roomtype)
        for house in ctx.houses:
            try:
                data = self._roomtypes_repo.get(house, pk=pk, user=ctx.users.get(house.company.id))
                if data != Nothing:
                    ctx.room_types.setdefault(house.id, []).append(data.unwrap())
                    return Success(ctx)
            except Exception as err:
                return self._error(
                    f"Error select Room Type ID={pk} for House ID={house.id}", ctx, OccupancyErrors.error, exc=err,
                )
        return self._error(f"Unknown Room Type ID={pk}", ctx, OccupancyErrors.missed_roomtype)

    @staticmethod
    def calculate_occupancy(ctx: Context) -> ResultE[Context]:
        if not ctx.room_types:
            return Success(ctx)
        for house_id, room_types in ctx.room_types.items():
            if not room_types:
                continue
            if house_id not in ctx.occupancies:
                ctx.occupancies[house_id] = {}
            for room_type in room_types:
                if room_type.id not in ctx.occupancies:
                    ctx.occupancies[house_id][room_type.id] = {}
                room_cnt = ctx.room_count.get(house_id, {}).get(room_type.id, 0)
                for day in cf.get_days_for_period(ctx.start_date, ctx.end_date):
                    busy_rooms = ctx.busy_days.get(house_id, {}).get(room_type.id, {}).get(day) or 0
                    ctx.occupancies[house_id][room_type.id][day] = room_cnt - busy_rooms
        return Success(ctx)

    @staticmethod
    def get_calendar_period(ctx: Context) -> ResultE[Context]:
        if ctx.start_date is None:
            # 2 days in past - for default Agenda view
            ctx.start_date = timezone.localdate() - datetime.timedelta(days=2)
        if ctx.end_date is None:
            ctx.end_date = timezone.localdate() + relativedelta.relativedelta(days=MAX_OCCUPANCY_PERIOD)
        if ctx.start_date > ctx.end_date:
            ctx.start_date = ctx.end_date
        return Success(ctx)

    def populate_roomtypes(self, ctx: Context) -> ResultE[Context]:
        if not ctx.room_types:
            return Success(ctx)
        for house_id, room_types in ctx.room_types.items():
            for room_type in room_types:
                try:
                    data = self._rooms_repo.get_count(house_id, room_type.id)
                    if house_id not in ctx.room_count:
                        ctx.room_count[house_id] = {}
                    ctx.room_count[house_id][room_type.id] = data
                except Exception as err:
                    return self._error(
                        f"Error select count of Rooms for Room Type ID={room_type.id}",
                        ctx,
                        OccupancyErrors.error,
                        exc=err,
                    )
        return Success(ctx)

    def save(self, ctx: Context) -> ResultE[Context]:
        if not ctx.occupancies:
            return Success(ctx)
        for house_id, room_types in ctx.room_types.items():
            if not ctx.occupancies.get(house_id, {}):
                continue
            for room_type in room_types:
                if not ctx.occupancies[house_id].get(room_type.id, {}):
                    continue
                try:
                    self._occupancy_repo.set(house_id, room_type.id, ctx.occupancies[house_id][room_type.id])
                except Exception as err:
                    return self._error(
                        f"Error save occupancy for Room Type ID={room_type.id} in House ID={house_id}",
                        ctx,
                        OccupancyErrors.error,
                        exc=err,
                    )
        return Success(ctx)

    def select_company_bots(self, ctx: Context) -> ResultE[Context]:
        if not ctx.houses:
            return Success(ctx)
        for house in ctx.houses:
            if house.company.id in ctx.users:
                continue
            try:
                data = self._members_repo.search_users(
                    criteria={'company': house.company.id, 'is_odoo_bot': True, 'odoo': True}
                )
                if not data:
                    return self._error(
                        f"Bot User not found for Company ID={house.company.id}", ctx, OccupancyErrors.missed_user,
                    )
                ctx.users[house.company.id] = data[0]
            except Exception as err:
                return self._error(
                    f"Error search Bot User for Company ID={house.company.id}", ctx, OccupancyErrors.error, exc=err,
                )
        return Success(ctx)

    def select_busy_days(self, ctx: Context) -> ResultE[Context]:
        if not ctx.room_types:
            return Success(ctx)
        for house_id, room_types in ctx.room_types.items():
            if not room_types:
                continue
            try:
                ctx.busy_days[house_id] = self._reservations_repo.select_busy_days(
                    house_id, [x.id for x in room_types], ctx.start_date, ctx.end_date
                )
            except Exception as err:
                return self._error(
                    f"Error select busy days for House ID={house_id}", ctx, OccupancyErrors.error, exc=err
                )
        return Success(ctx)

    def select_houses(self, ctx: Context) -> ResultE[Context]:
        try:
            if ctx.house_id is None:
                ctx.houses = self._houses_repo.select()
            else:
                pk = cf.get_int_or_none(ctx.house_id) or 0
                if pk <= 0:
                    return self._error('Wrong House ID', ctx, OccupancyErrors.missed_house)
                data = self._houses_repo.get(pk=pk)
                if data == Nothing:
                    return self._error(f"Unknown House ID={pk}", ctx, OccupancyErrors.missed_house)
                ctx.houses = [data.unwrap()]
            return Success(ctx)
        except Exception as err:
            return self._error('Error select houses', ctx, OccupancyErrors.error, exc=err)

    def select_roomtypes(self, ctx: Context) -> ResultE[Context]:
        if ctx.roomtype_id is not None:
            return self._select_specific_roomtype(ctx)
        return self._select_all_roomtypes(ctx)
