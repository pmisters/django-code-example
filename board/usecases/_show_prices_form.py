import dataclasses
from typing import List, TYPE_CHECKING

import inject
from returns.pipeline import flow
from returns.pointfree import bind_result
from returns.result import Success

from board.repositories import ReservationsRepo
from board.usecases.mixins import ReservationSelectMixin
from board.value_objects import ReservationErrors, ReservationPricesUpdateContext
from cancelations.repositories import PoliciesRepo
from common import functions as cf
from common.mixins import HouseSelectMixin
from common.value_objects import ResultE, ServiceBase
from house_prices.repositories import PricesRepo
from houses.repositories import HousesRepo, RoomTypesRepo, RoomsRepo

if TYPE_CHECKING:
    from board.entities import Reservation, ReservationRoom
    from cancelations.entities import Policy
    from house_prices.entities import RatePlan
    from houses.entities import House, RoomType, Room
    from members.entities import User


@dataclasses.dataclass
class Context:
    house_id: int
    pk: int
    room_id: int
    user: 'User'
    house: 'House' = None
    reservation: 'Reservation' = None
    reservation_room: 'ReservationRoom' = None
    rate_plans: List['RatePlan'] = dataclasses.field(default_factory=list)
    room_types: List['RoomType'] = dataclasses.field(default_factory=list)
    rooms: List['Room'] = dataclasses.field(default_factory=list)
    policies: List['Policy'] = dataclasses.field(default_factory=list)


class ShowPricesForm(ServiceBase, HouseSelectMixin, ReservationSelectMixin):
    @inject.autoparams()
    def __init__(
        self,
        houses_repo: HousesRepo,
        reservations_repo: ReservationsRepo,
        prices_repo: PricesRepo,
        roomtypes_repo: RoomTypesRepo,
        rooms_repo: RoomsRepo,
        policies_repo: PoliciesRepo,
    ):
        self._houses_repo = houses_repo
        self._reservations_repo = reservations_repo
        self._prices_repo = prices_repo
        self._roomtypes_repo = roomtypes_repo
        self._rooms_repo = rooms_repo
        self._policies_repo = policies_repo

        self._case_errors = ReservationErrors

    def execute(self, house_id: int, pk: int, room_id: int, user: 'User') -> ResultE[ReservationPricesUpdateContext]:
        ctx = Context(house_id=house_id, pk=pk, room_id=room_id, user=user)
        return flow(
            ctx,
            self.select_house,
            bind_result(self.select_reservation),
            bind_result(self.check_reservation),
            bind_result(self.select_reservation_room),
            bind_result(self.select_rate_plans),
            bind_result(self.select_cancellation_policies),
            bind_result(self.select_room_types),
            bind_result(self.select_rooms),
            bind_result(self.make_result),
        )

    def check_reservation(self, ctx: Context) -> ResultE[Context]:
        if ctx.reservation.house_id != ctx.house.id:
            return self._error(
                f"Reservation ID={ctx.reservation.id} has House ID={ctx.reservation.house_id} "
                f"but needs to be House ID={ctx.house.id}",
                ctx,
                self._case_errors.missed_reservation,
            )
        if not ctx.reservation.allow_update_prices():
            return self._error(
                f"Reservation ID={ctx.reservation.id} is not allowed to update prices",
                ctx,
                self._case_errors.missed_reservation,
            )
        return Success(ctx)

    @staticmethod
    def make_result(ctx: Context) -> ResultE[ReservationPricesUpdateContext]:
        return Success(
            ReservationPricesUpdateContext(
                house=ctx.house,
                reservation=ctx.reservation,
                reservation_room=ctx.reservation_room,
                rate_plans=ctx.rate_plans,
                room_types=ctx.room_types,
                rooms=ctx.rooms,
                policies=ctx.policies,
            )
        )

    def select_cancellation_policies(self, ctx: Context) -> ResultE[Context]:
        try:
            ctx.policies = self._policies_repo.select(ctx.house.id)
        except Exception as err:
            return self._error(
                f"Error select Cancellation Policies for House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        return Success(ctx)

    def select_rate_plans(self, ctx: Context) -> ResultE[Context]:
        try:
            ctx.rate_plans = self._prices_repo.select_plans(ctx.house, user=ctx.user)
        except Exception as err:
            return self._error(
                f"Error select Rate Plans for House ID={ctx.house.id}", ctx, self._case_errors.error, exc=err
            )
        return Success(ctx)

    def select_reservation_room(self, ctx: Context) -> ResultE[Context]:
        pk = cf.get_int_or_none(ctx.room_id) or 0
        if pk <= 0:
            return self._error('Missed Reservation Room ID', ctx, self._case_errors.missed_reservation)
        rooms = {x.id: x for x in ctx.reservation.rooms}
        if pk not in rooms:
            return self._error(
                f"Unknown Room ID={pk} in Reservation ID={ctx.reservation.id} House ID={ctx.house.id}",
                ctx,
                self._case_errors.missed_reservation,
            )
        ctx.reservation_room = rooms[pk]
        return Success(ctx)

    def select_room_types(self, ctx: Context) -> ResultE[Context]:
        try:
            ctx.room_types = self._roomtypes_repo.select(ctx.house, user=ctx.user, detailed=False)
        except Exception as err:
            return self._error(
                f"Error select Room Types for House ID={ctx.house.id}", ctx, self._case_errors.error, exc=err
            )
        return Success(ctx)

    def select_rooms(self, ctx: Context) -> ResultE[Context]:
        try:
            ctx.rooms = self._rooms_repo.select(ctx.house.id)
        except Exception as err:
            return self._error(
                f"Error select Rooms for House ID={ctx.house.id}", ctx, self._case_errors.error, exc=err
            )
        return Success(ctx)
