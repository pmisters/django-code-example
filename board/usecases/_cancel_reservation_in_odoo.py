import dataclasses
from typing import TYPE_CHECKING

import inject
from returns.maybe import Nothing
from returns.pipeline import flow
from returns.pointfree import bind_result
from returns.result import Success

from board.repositories import ReservationsRepo
from board.usecases.mixins import ReservationSelectMixin
from board.value_objects import ReservationErrors
from common import functions as cf
from common.mixins import HouseSelectMixin, OdooApiMixin
from common.value_objects import ResultE, ServiceBase
from effective_tours.constants import ReservationStatuses
from houses.repositories import HousesRepo
from members.repositories import MembersRepo
from odoo.value_objects import CrmLostReasons

if TYPE_CHECKING:
    from board.entities import Reservation
    from houses.entities import House
    from members.entities import User
    from odoo import OdooRPCAPI


@dataclasses.dataclass
class Context:
    house_id: int
    pk: int
    user_id: int = None
    house: 'House' = None
    user: 'User' = None
    reservation: 'Reservation' = None
    api: 'OdooRPCAPI' = None


class CancelReservationInOdoo(HouseSelectMixin, ReservationSelectMixin, OdooApiMixin, ServiceBase):
    @inject.autoparams()
    def __init__(self, houses_repo: HousesRepo, reservations_repo: ReservationsRepo, members_repo: MembersRepo):
        self._houses_repo = houses_repo
        self._reservations_repo = reservations_repo
        self._members_repo = members_repo

        self._case_errors = ReservationErrors

    def execute(self, house_id: int, pk: int, user_id: int = None) -> ResultE[bool]:
        ctx = Context(house_id=house_id, pk=pk, user_id=user_id)

        return flow(
            ctx,
            self.select_house,
            bind_result(self.select_reservation),
            bind_result(self.check_reservation),
            bind_result(self.select_user),
            bind_result(self.cancel_quotation),
            bind_result(self.cancel_opportunity),
            bind_result(lambda x: Success(True)),
        )

    def cancel_opportunity(self, ctx: Context) -> ResultE[Context]:
        """Cancel Opportunity (mark lost) in Odoo"""
        if ctx.reservation.opportunity_id is None or ctx.reservation.opportunity_id <= 0:
            # Reservation wasn't registered in Odoo
            return Success(ctx)
        try:
            self.get_rpc_api(ctx).cancel_opportunity(ctx.reservation.opportunity_id, CrmLostReasons.EXPENSIVE)
        except Exception as err:
            return self._error(
                f"Error cancel Opportunity ID={ctx.reservation.opportunity_id} "
                f"for Reservation ID={ctx.reservation.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        return Success(ctx)

    def cancel_quotation(self, ctx: Context) -> ResultE[Context]:
        """Cancel Quotation in Odoo"""
        if ctx.reservation.quotation_id is None or ctx.reservation.quotation_id <= 0:
            # Reservation wasn't registered in Odoo
            return Success(ctx)
        try:
            self.get_rpc_api(ctx).cancel_quotation(ctx.reservation.quotation_id)
        except Exception as err:
            return self._error(
                f"Error cancel Quotation ID={ctx.reservation.quotation_id} for Reservation ID={ctx.reservation.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        return Success(ctx)

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
                f"Reservation ID={ctx.reservation.id} is Room-Close and not registered in ODOO",
                ctx,
                self._case_errors.room_close_reservation,
            )
        if ctx.reservation.status != ReservationStatuses.CANCEL:
            return self._error(
                f"Reservation ID={ctx.reservation.id} is not Cancelled and can't be unregistered in ODOO",
                ctx,
                self._case_errors.missed_reservation,
            )
        return Success(ctx)

    def select_user(self, ctx: Context) -> ResultE[Context]:
        pk = cf.get_int_or_none(ctx.user_id) or 0
        try:
            if pk > 0:
                data = self._members_repo.get_user_by_id(pk)
            else:
                data = self._members_repo.get_bot_user(ctx.house.company.id)
        except Exception as err:
            return self._error(
                f"Error select User ID={pk} in Company ID={ctx.house.company.id}",
                ctx,
                self._case_errors.missed_user,
                exc=err,
            )
        if data == Nothing:
            return self._error(
                f"Unknown User ID={pk} in Company ID={ctx.house.company.id}", ctx, self._case_errors.missed_user
            )
        ctx.user = data.unwrap()
        return Success(ctx)
