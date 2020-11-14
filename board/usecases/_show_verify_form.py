import dataclasses
from typing import TYPE_CHECKING

import inject
from returns.pipeline import flow
from returns.pointfree import bind_result
from returns.result import Success

from board.repositories import ReservationsRepo
from board.usecases.mixins import ReservationSelectMixin
from board.value_objects import ReservationErrors, ReservationVerifyContext
from common.mixins import HouseSelectMixin
from common.value_objects import ResultE, ServiceBase
from effective_tours.constants import ReservationStatuses
from house_prices.repositories import PricesRepo
from houses.repositories import HousesRepo, RoomTypesRepo

if TYPE_CHECKING:
    from board.entities import Reservation
    from houses.entities import House
    from members.entities import User


@dataclasses.dataclass
class Context:
    house_id: int
    pk: int
    user: 'User'
    house: 'House' = None
    reservation: 'Reservation' = None


class ShowVerifyForm(ServiceBase, HouseSelectMixin, ReservationSelectMixin):
    @inject.autoparams()
    def __init__(
        self,
        houses_repo: HousesRepo,
        reservations_repo: ReservationsRepo,
        prices_repo: PricesRepo,
        roomtypes_repo: RoomTypesRepo,
    ):
        self._houses_repo = houses_repo
        self._reservations_repo = reservations_repo
        self._prices_repo = prices_repo
        self._roomtypes_repo = roomtypes_repo

        self._case_errors = ReservationErrors

    def execute(self, house_id: int, pk: int, user: 'User') -> ResultE[ReservationVerifyContext]:
        ctx = Context(house_id=house_id, pk=pk, user=user)
        return flow(
            ctx,
            self.select_house,
            bind_result(self.select_reservation),
            bind_result(self.check_reservation),
            bind_result(self.populate_with_plans),
            bind_result(self.populate_with_room_types),
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
        if ctx.reservation.status == ReservationStatuses.CLOSE:
            return self._error(
                f"Reservation ID={ctx.reservation.id} is Room-Close and can't be verified",
                ctx,
                self._case_errors.missed_reservation,
            )
        if not ctx.reservation.is_ota():
            return self._error(
                f"Reservation ID={ctx.reservation.id} is not from OTA and can't be verified",
                ctx,
                self._case_errors.missed_reservation,
            )
        if ctx.reservation.status == ReservationStatuses.CANCEL:
            return self._error(
                f"Reservation ID={ctx.reservation.id} is canceled and not need to be verified",
                ctx,
                self._case_errors.missed_reservation,
            )
        return Success(ctx)

    @staticmethod
    def make_result(ctx: Context) -> ResultE[ReservationVerifyContext]:
        return Success(ReservationVerifyContext(house=ctx.house, reservation=ctx.reservation))

    def populate_with_plans(self, ctx: Context) -> ResultE[Context]:
        plan_ids = [x.rate_plan_id for x in ctx.reservation.rooms if x.rate_plan_id is not None]
        plan_ids += [x.rate_plan_id_original for x in ctx.reservation.rooms if x.rate_plan_id_original is not None]
        if not plan_ids:
            return Success(ctx)
        try:
            plans = self._prices_repo.select_plans(ctx.house, ids=plan_ids, user=ctx.user)
        except Exception as err:
            return self._error(
                f"Error select Rate Plan ID={plan_ids} for House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        if not plans:
            return Success(ctx)
        plans = {x.id: x for x in plans}
        for room in ctx.reservation.rooms:
            room.rate_plan = plans.get(room.rate_plan_id)
            room.rate_plan_original = plans.get(room.rate_plan_id_original)
        return Success(ctx)

    def populate_with_room_types(self, ctx: Context) -> ResultE[Context]:
        try:
            room_types = self._roomtypes_repo.select(ctx.house, user=ctx.user, detailed=False)
        except Exception as err:
            return self._error(
                f"Error select Room Types for House ID={ctx.house.id}", ctx, self._case_errors.error, exc=err
            )
        if not room_types:
            return Success(ctx)
        room_types = {x.id: x for x in room_types}
        for room in ctx.reservation.rooms:
            for price in room.day_prices:
                price.room_type = room_types.get(price.roomtype_id)
        return Success(ctx)
