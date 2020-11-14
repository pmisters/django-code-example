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
from common.loggers import Logger
from common.mixins import HouseSelectMixin, OdooApiMixin
from common.value_objects import ResultE, ServiceBase
from effective_tours.constants import ChangelogActions, ReservationSources, ReservationStatuses
from houses.repositories import HousesRepo

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
    source: 'Reservation' = None
    reservation: 'Reservation' = None
    api: 'OdooRPCAPI' = None


class AcceptHoldReservation(HouseSelectMixin, ReservationSelectMixin, OdooApiMixin, ServiceBase):
    @inject.autoparams()
    def __init__(self, houses_repo: HousesRepo, reservations_repo: ReservationsRepo, changelog_repo: ChangelogRepo):
        self._houses_repo = houses_repo
        self._reservations_repo = reservations_repo
        self._changelog_repo = changelog_repo

        self._case_errors = ReservationErrors

    def execute(self, house_id: int, pk: int, user: 'User') -> ResultE[bool]:
        ctx = Context(house_id=house_id, pk=pk, user=user)

        return flow(
            ctx,
            self.select_house,
            bind_result(self.select_reservation),
            bind_result(self.check_reservation),
            bind_result(self.accept_reservation),
            bind_result(self.confirm_quotation),
            bind_result(self.write_changelog),
            bind_result(lambda x: Success(True)),
        )

    def accept_reservation(self, ctx: Context) -> ResultE[Context]:
        """Change reservation status to NEW and save to Repository"""
        if ctx.source.status != ReservationStatuses.HOLD:
            ctx.reservation = ctx.source
            return Success(ctx)
        ctx.reservation = attr.evolve(ctx.source, status=ReservationStatuses.NEW)
        try:
            data, __ = self._reservations_repo.save(ctx.reservation)
        except Exception as err:
            return self._error(
                f"Error save Reservation ID={ctx.reservation.id}", ctx, self._case_errors.error, exc=err
            )
        if data == Nothing:
            return self._error(
                f"Error save accepted Reservation ID={ctx.reservation.id}", ctx, self._case_errors.error
            )
        ctx.reservation = data.unwrap()
        return Success(ctx)

    def check_reservation(self, ctx: Context) -> ResultE[Context]:
        if ctx.source.house_id != ctx.house.id:
            return self._error(
                f"Reservation ID={ctx.source.id} has House ID={ctx.source.house_id} but need House ID={ctx.house.id}",
                ctx,
                self._case_errors.missed_reservation,
            )
        if ctx.source.source != ReservationSources.MANUAL:
            return self._error(
                f"Reservation ID={ctx.source.id} is from {ctx.source.source.value} and not acceptable",
                ctx,
                self._case_errors.missed_reservation,
            )
        if ctx.source.status == ReservationStatuses.CLOSE:
            return self._error(
                f"Reservation ID={ctx.source.id} is Room-Close and not acceptable",
                ctx,
                self._case_errors.missed_reservation,
            )
        return Success(ctx)

    def confirm_quotation(self, ctx: Context) -> ResultE[Context]:
        if ctx.reservation.quotation_id is None or ctx.reservation.quotation_id <= 0:
            # Do nothing if reservation hasn't Quatation
            return Success(ctx)
        try:
            self.get_rpc_api(ctx).confirm_quotation(ctx.reservation.quotation_id)
        except Exception as err:
            return self._error(
                f"Error update Quotation ID={ctx.reservation.quotation_id} for Reservation ID={ctx.reservation.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        return Success(ctx)

    def write_changelog(self, ctx: Context) -> ResultE[Context]:
        """Register changes made by User"""
        if ctx.source.status == ctx.reservation.status:
            # It wasn't HOLD reservation
            return Success(ctx)
        try:
            self._changelog_repo.create(
                ctx.user,
                ctx.source,
                ctx.reservation,
                ChangelogActions.UPDATE,
                house=ctx.house,
                message='User accept HOLD reservation',
            )
        except Exception as err:
            Logger.warning(__name__, f"Error register changelog: {err}")
        return Success(ctx)
