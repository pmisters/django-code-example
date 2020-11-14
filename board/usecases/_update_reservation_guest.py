import dataclasses
from typing import Any, TYPE_CHECKING

import attr
import inject
from returns.maybe import Nothing
from returns.pipeline import flow
from returns.pointfree import bind_result
from returns.result import Success

from board.repositories import ReservationsRepo
from board.usecases.mixins import ReservationSelectMixin
from board.value_objects import ReservationErrors
from common import functions as cf
from common.mixins import HouseSelectMixin
from common.value_objects import ResultE, ServiceBase
from effective_tours.constants import ReservationStatuses
from houses.repositories import HousesRepo

if TYPE_CHECKING:
    from board.entities import Reservation
    from houses.entities import House


@dataclasses.dataclass
class Context:
    house_id: int
    pk: int
    contact_id: int
    attribute: str
    value: Any
    house: 'House' = None
    source: 'Reservation' = None
    reservation: 'Reservation' = None


class UpdateReservationGuest(ServiceBase, HouseSelectMixin, ReservationSelectMixin):
    @inject.autoparams()
    def __init__(self, houses_repo: HousesRepo, reservations_repo: ReservationsRepo):
        self._houses_repo = houses_repo
        self._reservations_repo = reservations_repo

        self._case_errors = ReservationErrors

    def execute(self, house_id: int, pk: int, contact_id: int, attribute: str, value: Any) -> ResultE['Reservation']:
        ctx = Context(
            house_id=house_id,
            pk=pk,
            contact_id=cf.get_int_or_none(contact_id) or 0,
            attribute=(attribute or '').strip().lower(),
            value=value,
        )
        if ctx.contact_id <= 0:
            return self._error(
                f"Missed Contact ID for update Guest information in Reservation ID={ctx.pk}",
                ctx,
                self._case_errors.error,
            )
        if ctx.attribute == '':
            return self._error(
                f"Missed attribute for update Guest information in Reservation ID={ctx.pk}",
                ctx,
                self._case_errors.error,
            )
        if ctx.attribute not in ('name', 'email', 'phone'):
            return self._error(
                f"Unsupported attribute [{ctx.attribute}] for update Guest information in Reservation ID={ctx.pk}",
                ctx,
                self._case_errors.error,
            )
        return flow(
            ctx,
            self.select_house,
            bind_result(self.select_reservation),
            bind_result(self.check_reservation),
            bind_result(self.make_reservation_from_data),
            bind_result(self.save_reservation),
            bind_result(lambda x: Success(x.reservation)),
        )

    def check_reservation(self, ctx: Context) -> ResultE[Context]:
        if ctx.source.house_id != ctx.house.id:
            return self._error(
                f"Reservation ID={ctx.source.id} has House ID={ctx.source.house_id} "
                f"but needs to be House ID={ctx.house.id}",
                ctx,
                self._case_errors.missed_reservation,
            )
        if ctx.source.is_ota() or ctx.source.status == ReservationStatuses.CLOSE:
            return self._error(
                f"Reservation ID={ctx.source.id} is not allowed to update guest information",
                ctx,
                self._case_errors.missed_reservation,
            )
        return Success(ctx)

    @staticmethod
    def make_reservation_from_data(ctx: Context) -> ResultE[Context]:
        if ctx.source.guest_contact_id == 0 or ctx.contact_id != ctx.source.guest_contact_id:
            ctx.reservation = ctx.source
            return Success(ctx)

        if ctx.attribute == 'name':
            value = (ctx.value or '').strip().split(' ', maxsplit=1)
            ctx.reservation = attr.evolve(
                ctx.source, guest_name=value[0].strip(), guest_surname=value[1].strip() if len(value) > 1 else ''
            )
        elif ctx.attribute == 'email':
            ctx.reservation = attr.evolve(ctx.source, guest_email=ctx.value or '')
        elif ctx.attribute == 'phone':
            ctx.reservation = attr.evolve(ctx.source, guest_phone=ctx.value or '')
        else:
            ctx.reservation = ctx.source
        return Success(ctx)

    def save_reservation(self, ctx: Context) -> ResultE[Context]:
        if ctx.source.guest_contact_id == 0 or ctx.contact_id != ctx.source.guest_contact_id:
            # Don't save if there is not main contact
            return Success(ctx)
        try:
            data, __ = self._reservations_repo.save(ctx.reservation)
        except Exception as err:
            return self._error(
                f"Error save Reservation ID={ctx.reservation.id} in House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        if data == Nothing:
            return self._error(
                f"Error save guest information for Reservation ID={ctx.reservation.id} in House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
            )
        ctx.reservation = data.unwrap()
        return Success(ctx)
