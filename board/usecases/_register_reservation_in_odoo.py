import dataclasses
from typing import Any, Dict, List, TYPE_CHECKING

import inject
from returns.maybe import Nothing
from returns.pipeline import flow, is_successful
from returns.pointfree import bind_result
from returns.result import Success

from board.repositories import ReservationsRepo
from board.usecases.mixins import ReservationSelectMixin
from board.value_objects import ReservationErrors
from common import functions as cf
from common.mixins import HouseSelectMixin, OdooApiMixin
from common.value_objects import ResultE, ServiceBase
from contacts.usecases import CreateContact
from effective_tours.constants import ReservationStatuses
from houses.repositories import HousesRepo
from members.repositories import MembersRepo
from odoo.value_objects import CrmStages, CrmTags, CrmTeams, DATE_FORMAT

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
    api: 'OdooRPCAPI' = None


class RegisterReservationInOdoo(HouseSelectMixin, ReservationSelectMixin, OdooApiMixin, ServiceBase):
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
            bind_result(self.select_user),
            bind_result(self.check_reservation),
            bind_result(self.create_guest_contact),
            bind_result(self.create_opportunity),
            bind_result(self.create_quotation),
            bind_result(self.save_reservation),
            bind_result(lambda x: Success(True)),
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
                f"Reservation ID={ctx.reservation.id} is Room-Close and can't be registered in ODOO",
                ctx,
                self._case_errors.room_close_reservation,
            )
        return Success(ctx)

    def create_guest_contact(self, ctx: Context) -> ResultE[Context]:
        if ctx.reservation.guest_contact_id is not None and ctx.reservation.guest_contact_id > 0:
            # Contact was created before
            return Success(ctx)
        if ctx.reservation.get_guest_name() == '' or ctx.reservation.guest_email == '':
            return self._error(
                f"Reservation ID={ctx.reservation.id} hasn't guest contacts (name or email)",
                ctx,
                self._case_errors.missed_guest,
            )
        try:
            result = CreateContact().execute(
                ctx.house.id,
                ctx.reservation.get_guest_name(),
                ctx.reservation.guest_email,
                ctx.reservation.guest_phone,
                user=ctx.user,
            )
        except Exception as err:
            return self._error(
                f"Error create a Contact for a Reservation ID={ctx.reservation.id} in House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
                exc=err
            )
        if not is_successful(result):
            failure = result.failure()
            return self._error(failure.error, failure.ctx, self._case_errors.error, exc=failure.exc)

        contact = result.unwrap()
        ctx.reservation.guest_contact_id = contact.id
        ctx.reservation.guest_contact_ids.append(contact.id)
        return Success(ctx)

    def create_opportunity(self, ctx: Context) -> ResultE[Context]:
        if ctx.reservation.opportunity_id is not None and ctx.reservation.opportunity_id > 0:
            return Success(ctx)
        context = {'default_type': 'opportunity'}
        try:
            data = self.get_rpc_api(ctx).create_opportunity(self._prepare_opportunity_data(ctx), context=context)
        except Exception as err:
            return self._error(
                f"Error create Opportunity for Reservation ID={ctx.reservation.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        if data == Nothing:
            return self._error(
                f"Error create Opportunity for Reservation ID={ctx.reservation.id}", ctx, self._case_errors.error
            )
        ctx.reservation.opportunity_id = data.unwrap()
        return Success(ctx)

    def create_quotation(self, ctx: Context) -> ResultE[Context]:
        if ctx.reservation.quotation_id is not None and ctx.reservation.quotation_id > 0:
            return Success(ctx)
        try:
            data = self.get_rpc_api(ctx).create_quotation(
                self._prepare_quotation_data(ctx), self._prepare_quotation_items(ctx)
            )
        except Exception as err:
            return self._error(
                f"Error create Quotation for Reservation ID={ctx.reservation.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        if data == Nothing:
            return self._error(
                f"Error create Quotation for Reservation ID={ctx.reservation.id}", ctx, self._case_errors.error
            )
        ctx.reservation.quotation_id = data.unwrap()
        return Success(ctx)

    def save_reservation(self, ctx: Context) -> ResultE[Context]:
        try:
            data, __ = self._reservations_repo.save(ctx.reservation)
        except Exception as err:
            return self._error(
                f"Error save Reservation ID={ctx.reservation.id}", ctx, self._case_errors.error, exc=err
            )
        if data == Nothing:
            return self._error(f"Error save Reservation ID={ctx.reservation.id}", ctx, self._case_errors.save)
        ctx.reservation = data.unwrap()
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

    @staticmethod
    def _prepare_opportunity_data(ctx: Context) -> Dict[str, Any]:
        result = {
            'company_id': ctx.house.odoo_id,
            'name': ctx.reservation.get_opportunity_name(),
            'partner_id': ctx.reservation.guest_contact_id,
            'planned_revenue': str(ctx.reservation.price) if ctx.reservation.price is not None else None,
            'stage_id': CrmStages.NEGOTIATION.value,
            'team_id': CrmTeams.OTA.value if ctx.reservation.is_ota() else CrmTeams.SALES.value,
            'tag_ids': [],
        }
        source_tag = CrmTags.source_to_tag(ctx.reservation.source)
        if source_tag is not None:
            result['tag_ids'].append(source_tag.value)
        return result

    @staticmethod
    def _prepare_quotation_data(ctx: Context) -> Dict[str, Any]:
        return {
            'partner_id': ctx.reservation.guest_contact_id,
            'partner_invoice_id': ctx.reservation.guest_contact_id,
            'partner_shipping_id': ctx.reservation.guest_contact_id,
            'user_id': ctx.user.odoo_id,
            'currency_id': ctx.house.currency.odoo_id,
            'note': '',
            'company_id': ctx.house.odoo_id,
            'team_id': CrmTeams.OTA.value if ctx.reservation.is_ota() else CrmTeams.SALES.value,
            'opportunity_id': ctx.reservation.opportunity_id,
            'report_grids': True,
            'origin': ctx.reservation.id,
            'client_order_ref': ctx.reservation.channel_id if ctx.reservation.is_ota() else '',
        }

    @staticmethod
    def _prepare_quotation_items(ctx: Context) -> List[Dict[str, Any]]:
        result = []
        for room in ctx.reservation.rooms:
            for price in room.day_prices:
                if price.roomtype_id is None:
                    continue
                result.append(
                    {
                        'price_unit': str(price.price_accepted),
                        'order_partner_id': ctx.reservation.guest_contact_id,
                        'discount': 0.,
                        'product_id': price.roomtype_id,
                        'product_uom_qty': 1,
                        'item_date': price.day.strftime(DATE_FORMAT),
                    }
                )
        return result
