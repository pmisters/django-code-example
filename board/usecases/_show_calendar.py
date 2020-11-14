import dataclasses
import datetime
from typing import Dict, List, Optional, TYPE_CHECKING

import inject
from dateutil import rrule
from returns.pipeline import flow
from returns.pointfree import bind_result
from returns.result import Success

from board.value_objects import CalendarContext, CalendarErrors
from common.mixins import CalendarMixin, HouseSelectMixin
from common.value_objects import ResultE, ServiceBase
from houses.repositories import HousesRepo, RoomTypesRepo, RoomsRepo

if TYPE_CHECKING:
    from houses.entities import House, Room, RoomTypeDetails
    from members.entities import User


@dataclasses.dataclass
class Context:
    house_id: int
    base_date: datetime.date = None
    user: 'User' = None
    house: 'House' = None
    start_date: datetime.date = None
    end_date: datetime.date = None
    dates: Dict[int, List[datetime.date]] = dataclasses.field(default_factory=dict)
    room_types: List['RoomTypeDetails'] = dataclasses.field(default_factory=list)
    rooms: List['Room'] = dataclasses.field(default_factory=list)


class ShowCalendar(ServiceBase, HouseSelectMixin, CalendarMixin):
    @inject.autoparams()
    def __init__(self, houses_repo: HousesRepo, roomtypes_repo: RoomTypesRepo, rooms_repo: RoomsRepo):
        self._houses_repo = houses_repo
        self._roomtypes_repo = roomtypes_repo
        self._rooms_repo = rooms_repo

        self._case_errors = CalendarErrors

    def execute(self, pk: int, base_date: Optional[datetime.date], user: 'User' = None) -> ResultE[CalendarContext]:
        ctx = Context(house_id=pk, base_date=base_date, user=user)
        return flow(
            ctx,
            self.select_house,
            bind_result(self.get_calendar_period),
            bind_result(self.get_calendar_dates),
            bind_result(self.select_roomtypes),
            bind_result(self.select_rooms),
            bind_result(self.make_result),
        )

    @staticmethod
    def get_calendar_dates(ctx: Context) -> ResultE[Context]:
        days = list(rrule.rrule(rrule.DAILY, dtstart=ctx.start_date, until=ctx.end_date))
        ctx.dates = {}
        for day in days:
            ctx.dates.setdefault(day.month, []).append(day.date())
        return Success(ctx)

    @staticmethod
    def make_result(ctx: Context) -> ResultE[CalendarContext]:
        return Success(
            CalendarContext(
                house=ctx.house,
                base_date=ctx.base_date,
                start_date=ctx.start_date,
                end_date=ctx.end_date,
                dates=ctx.dates,
                room_types=ctx.room_types,
                rooms=ctx.rooms,
            )
        )

    def select_rooms(self, ctx: Context) -> ResultE[Context]:
        try:
            ctx.rooms = self._rooms_repo.select(ctx.house.id)
            return Success(ctx)
        except Exception as err:
            return self._error(
                f"Error select Rooms for House ID={ctx.house.id}", ctx, self._case_errors.error, exc=err
            )

    def select_roomtypes(self, ctx: Context) -> ResultE[Context]:
        try:
            ctx.room_types = self._roomtypes_repo.select(ctx.house, user=ctx.user, detailed=True)
            return Success(ctx)
        except Exception as err:
            return self._error(
                f"Error select Room Types for House ID={ctx.house.id}", ctx, self._case_errors.error, exc=err
            )
