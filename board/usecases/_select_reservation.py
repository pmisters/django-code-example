import dataclasses
from decimal import Decimal
from typing import TYPE_CHECKING

import inject
from returns.pipeline import flow
from returns.pointfree import bind_result
from returns.result import Success

from board.repositories import ReservationsRepo
from board.value_objects import ReservationDetailsContext, ReservationErrors
from common import functions as cf
from common.mixins import HouseSelectMixin, OdooApiMixin, ReservationSelectMixin
from common.value_objects import ResultE, ServiceBase
from effective_tours.constants import ReservationStatuses
from house_prices.repositories import PricesRepo
from houses.repositories import HousesRepo, RoomTypesRepo, RoomsRepo

if TYPE_CHECKING:
    from board.entities import Reservation
    from houses.entities import House
    from members.entities import User
    from odoo import OdooRPCAPI


@dataclasses.dataclass
class Context:
    house_id: int
    pk: int
    user: 'User'
    house: 'House' = None
    reservation: 'Reservation' = None
    payed_amount: Decimal = Decimal(0)
    api: 'OdooRPCAPI' = None


class SelectReservation(HouseSelectMixin, ReservationSelectMixin, OdooApiMixin, ServiceBase):
    @inject.autoparams()
    def __init__(
        self,
        houses_repo: HousesRepo,
        reservations_repo: ReservationsRepo,
        prices_repo: PricesRepo,
        roomtypes_repo: RoomTypesRepo,
        rooms_repo: RoomsRepo,
    ):
        self._houses_repo = houses_repo
        self._reservations_repo = reservations_repo
        self._prices_repo = prices_repo
        self._roomtypes_repo = roomtypes_repo
        self._rooms_repo = rooms_repo

        self._case_errors = ReservationErrors

    def execute(self, house_id: int, pk: int, user: 'User') -> ResultE[ReservationDetailsContext]:
        ctx = Context(house_id=house_id, pk=pk, user=user)
        return flow(
            ctx,
            self.select_house,
            bind_result(self.select_reservation),
            bind_result(self.check_reservation),
            bind_result(self.populate_with_rate_plans),
            bind_result(self.populate_with_room_types),
            bind_result(self.populate_with_rooms),
            bind_result(self.select_payed_amount),
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
                f"Reservation ID={ctx.reservation.id} is Room-Close", ctx, self._case_errors.missed_reservation
            )
        return Success(ctx)

    @staticmethod
    def make_result(ctx: Context) -> ResultE[ReservationDetailsContext]:
        return Success(
            ReservationDetailsContext(house=ctx.house, reservation=ctx.reservation, payed_amount=ctx.payed_amount)
        )

    def populate_with_rate_plans(self, ctx: Context) -> ResultE[Context]:
        plan_ids = [x.rate_plan_id for x in ctx.reservation.rooms if x.rate_plan_id is not None]
        if not plan_ids:
            return Success(ctx)
        try:
            data = self._prices_repo.select_plans(ctx.house, ids=list(set(plan_ids)), user=ctx.user)
        except Exception as err:
            return self._error(
                f"Error select Rate Plans in House ID={ctx.house.id}", ctx, self._case_errors.error, exc=err
            )
        if not data:
            return Success(ctx)
        plans = {x.id: x for x in data}
        for room in ctx.reservation.rooms:
            if room.rate_plan_id is not None and room.rate_plan_id in plans:
                room.rate_plan = plans[room.rate_plan_id]
        return Success(ctx)

    def populate_with_room_types(self, ctx: Context) -> ResultE[Context]:
        try:
            room_types = self._roomtypes_repo.select(ctx.house, user=ctx.user)
        except Exception as err:
            return self._error(
                f"Error select Room Types from House ID={ctx.house.id}", ctx, self._case_errors.error, exc=err
            )
        if not room_types:
            return self._error(f"Empty list of Room Types in House ID={ctx.house.id}", ctx, self._case_errors.error)
        room_types = {x.id: x for x in room_types}
        for room in ctx.reservation.rooms:
            for price in room.day_prices:
                price.room_type = room_types.get(price.roomtype_id) if price.roomtype_id is not None else None
        return Success(ctx)

    def populate_with_rooms(self, ctx: Context) -> ResultE[Context]:
        room_ids = []
        for room in ctx.reservation.rooms:
            room_ids += [x.room_id for x in room.day_prices if x.room_id is not None]
        if not room_ids:
            return Success(ctx)
        try:
            rooms = self._rooms_repo.select(ctx.house.id, ids=room_ids)
        except Exception as err:
            return self._error(
                f"Error select Rooms for House ID={ctx.house.id}", ctx, self._case_errors.error, exc=err
            )
        if not rooms:
            return Success(ctx)
        rooms = {x.id: x for x in rooms}
        for room in ctx.reservation.rooms:
            for price in room.day_prices:
                price.room = rooms.get(price.room_id) if price.room_id is not None else None
        return Success(ctx)

    def select_payed_amount(self, ctx: Context) -> ResultE[Context]:
        if ctx.reservation.quotation_id is None or ctx.reservation.quotation_id <= 0:
            return Success(ctx)
        try:
            invoices = self.get_rpc_api(ctx).select_invoices_for_order(ctx.reservation.quotation_id)
        except Exception as err:
            return self._error(
                f"Error select Invoices for Quotation ID={ctx.reservation.quotation_id} "
                f"for Reservation ID={ctx.reservation.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        if not invoices:
            return Success(ctx)
        ctx.payed_amount = sum(
            [cf.get_decimal_or_none(x.amount_total - x.amount_residual) or Decimal(0) for x in invoices]
        )
        return Success(ctx)
