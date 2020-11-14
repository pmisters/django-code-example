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
    house: 'House' = None
    reservation: 'Reservation' = None


class AttachContactToReservation(ServiceBase, HouseSelectMixin, ReservationSelectMixin):
    @inject.autoparams()
    def __init__(self, houses_repo: HousesRepo, reservations_repo: ReservationsRepo):
        self._houses_repo = houses_repo
        self._reservations_repo = reservations_repo

        self._case_errors = ReservationErrors

    def execute(self, house_id: int, pk: int, contact_id: int) -> ResultE[bool]:
        ctx = Context(house_id=house_id, pk=pk, contact_id=contact_id)
        return flow(
            ctx,
            self.select_house,
            bind_result(self.select_reservation),
            bind_result(self.check_reservation),
            bind_result(self.add_contact),
            bind_result(self.save),
            bind_result(lambda x: Success(True)),
        )

    @staticmethod
    def add_contact(ctx: Context) -> ResultE[Context]:
        if ctx.reservation.guest_contact_id is None:
            ctx.reservation.guest_contact_id = ctx.contact_id
        if ctx.reservation.guest_contact_ids is None:
            ctx.reservation.guest_contact_ids = []
        ctx.reservation.guest_contact_ids.append(ctx.contact_id)
        ctx.reservation.guest_contact_ids = sorted(list(set(ctx.reservation.guest_contact_ids)))
        return Success(ctx)

    def save(self, ctx: Context) -> ResultE[Context]:
        try:
            data, __ = self._reservations_repo.save(ctx.reservation)
        except Exception as err:
            return self._error(
                f"Error save Reservation ID={ctx.reservation.id} for House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        if data == Nothing:
            return self._error(
                f"Error save Reservation ID={ctx.reservation.id} for House ID={ctx.house.id}",
                ctx,
                self._case_errors.save,
            )
        ctx.reservation = data.unwrap()
        return Success(ctx)

    def check_reservation(self, ctx: Context) -> ResultE[Context]:
        if ctx.reservation.status == ReservationStatuses.CLOSE:
            return self._error(
                f"Guest Contact can't be attached to Room-Close Reservation ID={ctx.reservation.id} "
                f"in House ID={ctx.house.id}",
                ctx,
                self._case_errors.missed_reservation,
            )
        return Success(ctx)
