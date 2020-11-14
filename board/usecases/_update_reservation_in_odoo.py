import dataclasses
from typing import Any, Dict, List, TYPE_CHECKING

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
from odoo.value_objects import DATE_FORMAT

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
    reservation: 'Reservation' = None
    user: 'User' = None
    is_need_update_quotation: bool = True
    is_locked_quotation: bool = False
    api: 'OdooRPCAPI' = None


class UpdateReservationInOdoo(HouseSelectMixin, ReservationSelectMixin, OdooApiMixin, ServiceBase):
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
            bind_result(self.update_opportunity),
            bind_result(self.check_need_update_quotation),
            bind_result(self.get_quotation_state),
            bind_result(self.unlock_quotation),
            bind_result(self.update_quotation),
            bind_result(self.lock_back_quotation),
            bind_result(lambda x: Success(True)),
        )

    def check_need_update_quotation(self, ctx: Context) -> ResultE[Context]:
        if ctx.reservation.quotation_id is None or ctx.reservation.quotation_id <= 0:
            ctx.is_need_update_quotation = False
            return Success(ctx)
        try:
            data = self.get_rpc_api(ctx).get_quotation_items(ctx.reservation.quotation_id)
        except Exception as err:
            return self._error(
                f"Error select items of Quotation ID={ctx.reservation.quotation_id} "
                f"for Reservation ID={ctx.reservation.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        current_items = []
        for item in data:
            current_items.append(
                {
                    'product_id': item['product_id'][0],
                    'item_date': item['item_date'],
                    'product_uom_qty': item['product_uom_qty'],
                    'price_unit': item['price_unit'],
                }
            )
        updated_items = self._prepare_quotation_items(ctx.reservation)
        ctx.is_need_update_quotation = not (current_items == updated_items)
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
                f"Reservation ID={ctx.reservation.id} is Room-Close and isn't registered in ODOO",
                ctx,
                self._case_errors.room_close_reservation,
            )
        return Success(ctx)

    def get_quotation_state(self, ctx: Context) -> ResultE[Context]:
        if not ctx.is_need_update_quotation:
            return Success(ctx)
        try:
            data = self.get_rpc_api(ctx).get_quotation(ctx.reservation.quotation_id)
        except Exception as err:
            return self._error(
                f"Error select Quotation ID={ctx.reservation.quotation_id} for Reservation ID={ctx.reservation.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        if data == Nothing:
            return self._error(
                f"Missed Quotation ID={ctx.reservation.quotation_id} for Reservation ID={ctx.reservation.id}",
                ctx,
                self._case_errors.error,
            )
        quotation = data.unwrap()
        ctx.is_locked_quotation = (quotation.state or '').strip().lower() == 'done'
        return Success(ctx)

    def lock_back_quotation(self, ctx: Context) -> ResultE[Context]:
        if not ctx.is_need_update_quotation or not ctx.is_locked_quotation:
            return Success(ctx)
        try:
            self.get_rpc_api(ctx).confirm_quotation(ctx.reservation.quotation_id)
        except Exception as err:
            return self._error(
                f"Error lock back Quotation ID={ctx.reservation.quotation_id} "
                f"for Reservation ID={ctx.reservation.id}",
                ctx,
                self._case_errors.error,
                exc=err,
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

    def unlock_quotation(self, ctx: Context) -> ResultE[Context]:
        if not ctx.is_need_update_quotation or not ctx.is_locked_quotation:
            return Success(ctx)
        try:
            self.get_rpc_api(ctx).unlock_quotation(ctx.reservation.quotation_id)
        except Exception as err:
            return self._error(
                f"Error unlock Quotation ID={ctx.reservation.quotation_id} for Reservation ID={ctx.reservation.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        return Success(ctx)

    def update_opportunity(self, ctx: Context) -> ResultE[Context]:
        if ctx.reservation.opportunity_id is None or ctx.reservation.opportunity_id <= 0:
            return Success(ctx)
        try:
            data = {
                'name': ctx.reservation.get_opportunity_name(),
                'planned_revenue': (
                    str(ctx.reservation.price_accepted) if ctx.reservation.price_accepted is not None else None
                ),
            }
            self.get_rpc_api(ctx).update_opportunity(ctx.reservation.opportunity_id, data)
        except Exception as err:
            return self._error(
                f"Error update Opportunity ID={ctx.reservation.opportunity_id} "
                f"for Reservation ID={ctx.reservation.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        return Success(ctx)

    def update_quotation(self, ctx: Context) -> ResultE[Context]:
        if not ctx.is_need_update_quotation:
            return Success(ctx)
        items_data = self._prepare_quotation_items(ctx.reservation)
        try:
            self.get_rpc_api(ctx).update_quotation_items(ctx.reservation.quotation_id, items_data)
        except Exception as err:
            return self._error(
                f"Error update Quotation ID={ctx.reservation.quotation_id} for Reservation ID={ctx.reservation.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        return Success(ctx)

    @staticmethod
    def _prepare_quotation_items(reservation: 'Reservation') -> List[Dict[str, Any]]:
        result = []
        for room in reservation.rooms:
            for price in room.day_prices:
                if price.roomtype_id is None:
                    continue
                result.append(
                    {
                        'product_id': price.roomtype_id,
                        'item_date': price.day.strftime(DATE_FORMAT),
                        'product_uom_qty': 1.0,
                        'price_unit': float(price.price_accepted),
                    }
                )
        return result
