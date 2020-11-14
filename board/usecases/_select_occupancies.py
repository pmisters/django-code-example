import dataclasses
import datetime
from typing import Dict, List, Optional, TYPE_CHECKING

import inject
from dateutil import rrule
from returns.pipeline import flow
from returns.pointfree import bind_result
from returns.result import Success

from board.repositories import OccupancyRepo
from board.value_objects import CalendarErrors, OccupanciesContext
from common.mixins import CalendarMixin, HouseSelectMixin
from common.value_objects import ResultE, ServiceBase
from houses.repositories import HousesRepo, RoomTypesRepo

if TYPE_CHECKING:
    from houses.entities import House, RoomType
    from members.entities import User


@dataclasses.dataclass
class Context:
    house_id: int
    base_date: datetime.date = None
    user: 'User' = None
    house: 'House' = None
    start_date: datetime.date = None
    end_date: datetime.date = None
    room_types: List['RoomType'] = dataclasses.field(default_factory=list)
    occupancies: Dict[int, Dict[datetime.date, Optional[int]]] = dataclasses.field(default_factory=dict)


class SelectOccupancies(ServiceBase, HouseSelectMixin, CalendarMixin):
    @inject.autoparams()
    def __init__(self, houses_repo: HousesRepo, roomtypes_repo: RoomTypesRepo, occupancy_repo: OccupancyRepo):
        self._houses_repo = houses_repo
        self._roomtypes_repo = roomtypes_repo
        self._occupancy_repo = occupancy_repo

        self._case_errors = CalendarErrors

    def execute(
        self, pk: int, base_date: Optional[datetime.date], user: 'User' = None
    ) -> ResultE[OccupanciesContext]:
        ctx = Context(house_id=pk, base_date=base_date, user=user)
        return flow(
            ctx,
            self.select_house,
            bind_result(self.get_calendar_period),
            bind_result(self.select_roomtypes),
            bind_result(self.select_occupancies),
            bind_result(self.make_result),
        )

    @staticmethod
    def make_result(ctx: Context) -> ResultE[OccupanciesContext]:
        return Success(
            OccupanciesContext(start_date=ctx.start_date, end_date=ctx.end_date, occupancies=ctx.occupancies)
        )

    def select_occupancies(self, ctx: Context) -> ResultE[Context]:
        days = list(rrule.rrule(rrule.DAILY, dtstart=ctx.start_date, until=ctx.end_date))
        dates = [x.date() for x in days]
        for room_type in ctx.room_types:
            try:
                ctx.occupancies[room_type.id] = self._occupancy_repo.get(ctx.house.id, room_type.id, dates)
            except Exception as err:
                return self._error(
                    f"Error get occupancies for Room Type ID={room_type.id}", ctx, self._case_errors.error, exc=err
                )
        return Success(ctx)

    def select_roomtypes(self, ctx: Context) -> ResultE[Context]:
        try:
            ctx.room_types = self._roomtypes_repo.select(ctx.house, user=ctx.user, detailed=True)
            return Success(ctx)
        except Exception as err:
            return self._error(
                f"Error select Room Types for House ID={ctx.house.id}", ctx, self._case_errors.error, exc=err
            )
