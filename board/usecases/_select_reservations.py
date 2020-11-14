import dataclasses
import datetime
from typing import List, Optional, TYPE_CHECKING

import inject
from returns.pipeline import flow
from returns.pointfree import bind_result
from returns.result import Success

from board.repositories import ReservationsCacheRepo
from board.value_objects import CachedReservation, ReservationErrors
from common import functions as cf
from common.mixins import CalendarMixin, HouseSelectMixin
from common.value_objects import ResultE, ServiceBase
from houses.repositories import HousesRepo

if TYPE_CHECKING:
    from houses.entities import House


@dataclasses.dataclass
class Context:
    house_id: int
    base_date: datetime.date = None
    start_date: datetime.date = None
    end_date: datetime.date = None
    house: 'House' = None
    reservations: List[CachedReservation] = dataclasses.field(default_factory=list)


class SelectReservations(ServiceBase, HouseSelectMixin, CalendarMixin):
    @inject.autoparams()
    def __init__(self, houses_repp: HousesRepo, cache_repo: ReservationsCacheRepo):
        self._houses_repo = houses_repp
        self._cache_repo = cache_repo

        self._case_errors = ReservationErrors

    def execute(self, house_id: int, base_date: Optional[datetime.date]) -> ResultE[List[CachedReservation]]:
        ctx = Context(house_id=house_id, base_date=base_date)
        return flow(
            ctx,
            self.select_house,
            bind_result(self.get_calendar_period),
            bind_result(self.read_reservations),
            bind_result(self.filter_reservations),
            bind_result(self.make_result),
        )

    @staticmethod
    def filter_reservations(ctx: Context) -> ResultE[Context]:
        ctx.reservations = [
            x for x in ctx.reservations if x.checkout.date() > ctx.start_date and x.checkin.date() <= ctx.end_date
        ]
        return Success(ctx)

    @staticmethod
    def make_result(ctx: Context) -> ResultE[List[CachedReservation]]:
        for reservation in ctx.reservations:
            reservation.daystart = (reservation.checkin.date() - ctx.start_date).days
            if reservation.daystart < 0:
                reservation.daystart = -1
            reservation.dayend = (min(reservation.checkout.date(), ctx.end_date) - ctx.start_date).days
        return Success(ctx.reservations)

    def read_reservations(self, ctx: Context) -> ResultE[Context]:
        house_id = cf.get_int_or_none(ctx.house_id) or 0
        if house_id <= 0:
            return self._error('Missed House ID', ctx, self._case_errors.missed_house)
        try:
            ctx.reservations = self._cache_repo.search(house_id)
            return Success(ctx)
        except Exception as err:
            return self._error(
                f"Error select reservations from Cache for House ID={house_id}", ctx, self._case_errors.error, exc=err
            )
