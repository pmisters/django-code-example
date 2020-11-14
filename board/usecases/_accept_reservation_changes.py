import dataclasses
from typing import List, TYPE_CHECKING

import inject
from returns.maybe import Nothing
from returns.pipeline import flow
from returns.pointfree import bind_result
from returns.result import Success

from action_logger.repositories import ChangelogRepo
from board.repositories import ReservationsRepo
from board.usecases.mixins import ReservationSelectMixin
from board.value_objects import ReservationErrors
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
    house_id: int
    pk: int
    user: 'User'
    price_ids: List[int] = dataclasses.field(default_factory=list)
    house: 'House' = None
    source: 'Reservation' = None
    reservation: 'Reservation' = None


class AcceptReservationChanges(ServiceBase, HouseSelectMixin, ReservationSelectMixin):
    @inject.autoparams()
    def __init__(self, houses_repo: HousesRepo, reservations_repo: ReservationsRepo, changelog_repo: ChangelogRepo):
        self._houses_repo = houses_repo
        self._reservations_repo = reservations_repo
        self._changelog_repo = changelog_repo

        self._case_errors = ReservationErrors

    def execute(self, house_id: int, pk: int, user: 'User', price_ids: List[int] = None) -> ResultE['Reservation']:
        ctx = Context(house_id=house_id, pk=pk, user=user, price_ids=price_ids or [])
        return flow(
            ctx,
            self.select_house,
            bind_result(self.select_reservation),
            bind_result(self.check_reservation),
            bind_result(self.accept_changes),
            bind_result(self.write_changelog),
            bind_result(lambda x: Success(ctx.reservation)),
        )

    def accept_changes(self, ctx: Context) -> ResultE[Context]:
        if ctx.source.is_verified:
            ctx.reservation = ctx.source
            return Success(ctx)
        try:
            data = self._reservations_repo.accept(ctx.source.id, price_ids=ctx.price_ids)
        except Exception as err:
            return self._error(
                f"Error accept changes for Reservation ID={ctx.source.id} in House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        if data == Nothing:
            return self._error(
                f"Error accept changes for Reservation ID={ctx.source.id} in House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
            )
        ctx.reservation = data.unwrap()
        return Success(ctx)

    def check_reservation(self, ctx: Context) -> ResultE[Context]:
        if ctx.source.house_id != ctx.house.id:
            return self._error(
                f"Reservation ID={ctx.source.id} has House ID={ctx.source.house_id} "
                f"but should be House ID={ctx.house.id}",
                ctx,
                self._case_errors.missed_reservation,
            )
        if ctx.source.status == ReservationStatuses.CLOSE:
            return self._error(
                f"Reservation ID={ctx.source.id} is Room-Close and can't be verified",
                ctx,
                self._case_errors.missed_reservation,
            )
        elif ctx.source.status == ReservationStatuses.CANCEL:
            return self._error(
                f"Reservation ID={ctx.source.id} is canceled and not need to be verified",
                ctx,
                self._case_errors.missed_reservation,
            )
        if not ctx.source.is_ota():
            return self._error(
                f"Reservation ID={ctx.source.id} is not from OTA and can't be verified",
                ctx,
                self._case_errors.missed_reservation,
            )
        return Success(ctx)

    def write_changelog(self, ctx: Context) -> ResultE[Context]:
        if ctx.source.is_verified:
            # Reservation was verified before
            return Success(ctx)
        try:
            self._changelog_repo.create(
                ctx.user,
                ctx.source,
                ctx.reservation,
                ChangelogActions.UPDATE,
                house=ctx.house,
                message=f"Accept changes in Reservation {ctx.reservation.get_id()}"
            )
        except Exception as err:
            Logger.warning(__name__, f"Error write changelog : {err}")
        return Success(ctx)
