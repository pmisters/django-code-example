import dataclasses
from typing import TYPE_CHECKING

import attr
import inject
from returns.maybe import Nothing
from returns.pipeline import flow
from returns.pointfree import bind_result
from returns.result import Success

from action_logger.repositories import ChangelogRepo
from board.repositories import ReservationsRepo
from board.usecases.mixins import ReservationSelectMixin
from board.value_objects import ReservationErrors
from common import functions as cf
from common.loggers import Logger
from common.mixins import HouseSelectMixin
from common.value_objects import ResultE, ServiceBase
from effective_tours.constants import ChangelogActions, ReservationStatuses
from houses.repositories import HousesRepo

if TYPE_CHECKING:
    from board.entities import Reservation
    from houses.entities import House
    from members.entities import User


@dataclasses.dataclass
class Context:
    pk: int
    house_id: int
    user: 'User'
    house: 'House' = None
    reservation: 'Reservation' = None


class DeleteRoomClose(ServiceBase, HouseSelectMixin, ReservationSelectMixin):
    @inject.autoparams()
    def __init__(self, houses_repo: HousesRepo, reservations_repo: ReservationsRepo, changelog_repo: ChangelogRepo):
        self._houses_repo = houses_repo
        self._reservations_repo = reservations_repo
        self._changelog_repo = changelog_repo

        self._case_errors = ReservationErrors

    def execute(self, pk: str, house_id: int, user: 'User') -> ResultE['Reservation']:
        pk = cf.get_int_or_none((pk or '').split('-')[0]) or 0
        ctx = Context(pk=pk, house_id=house_id, user=user)
        return flow(
            ctx,
            self.select_house,
            bind_result(self.select_reservation),
            bind_result(self.check_reservation),
            bind_result(self.make_reservation_from_data),
            bind_result(self.save_reservation),
            bind_result(self.write_changelog),
            bind_result(lambda x: Success(x.reservation)),
        )

    @staticmethod
    def make_reservation_from_data(ctx: Context) -> ResultE[Context]:
        ctx.reservation = attr.evolve(ctx.reservation, status=ReservationStatuses.CANCEL)
        return Success(ctx)

    def save_reservation(self, ctx: Context) -> ResultE[Context]:
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
                f"Error save Reservation ID={ctx.reservation.id} in House ID={ctx.house.id}",
                ctx,
                self._case_errors.save,
            )
        ctx.reservation = data.unwrap()
        return Success(ctx)

    def check_reservation(self, ctx: Context) -> ResultE[Context]:
        """Check if reservation can be canceled"""
        if ctx.reservation.house_id != ctx.house.id:
            return self._error(
                f"Reservation ID={ctx.reservation.id} has House ID={ctx.reservation.house_id} "
                f"but needs to be House ID={ctx.house.id}",
                ctx,
                self._case_errors.missed_reservation,
            )
        if ctx.reservation.status != ReservationStatuses.CLOSE:
            return self._error(
                f"Reservation ID={ctx.reservation.id} has wrong status", ctx, self._case_errors.missed_reservation
            )
        return Success(ctx)

    def write_changelog(self, ctx: Context) -> ResultE[Context]:
        try:
            self._changelog_repo.create_manual(
                ctx.user,
                ctx.reservation,
                ChangelogActions.DELETE,
                changes={'status': (ReservationStatuses.CLOSE.value, ReservationStatuses.CANCEL.value)},
                house=ctx.house,
                message=(
                    f"Open room for {ctx.reservation.checkin.isoformat()}..{ctx.reservation.checkout.isoformat()}"
                ),
            )
        except Exception as err:
            Logger.warning(__name__, f"Error write changelog: {err}")
        return Success(ctx)
