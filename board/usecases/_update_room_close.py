import dataclasses
import datetime
from typing import TYPE_CHECKING

import attr
import inject
from returns.maybe import Nothing
from returns.pipeline import flow
from returns.pointfree import bind_result
from returns.result import Success

from action_logger.repositories import ChangelogRepo
from board.entities import ReservationDay
from board.repositories import ReservationsRepo
from board.usecases.mixins import ReservationSelectMixin
from board.value_objects import ReservationErrors, ReservationUpdateContext
from common import functions as cf
from common.loggers import Logger
from common.mixins import HouseSelectMixin, RoomSelectMixin
from common.value_objects import ResultE, ServiceBase
from effective_tours.constants import ChangelogActions, ReservationStatuses, RoomCloseReasons
from houses.repositories import HousesRepo, RoomsRepo

if TYPE_CHECKING:
    from board.entities import Reservation
    from houses.entities import House, Room
    from members.entities import User


@dataclasses.dataclass
class Context:
    pk: int
    house_id: int
    room_id: int
    start_date: datetime.date
    end_date: datetime.date
    reason: RoomCloseReasons
    user: 'User'
    notes: str = ''
    house: 'House' = None
    room: 'Room' = None
    source: 'Reservation' = None
    reservation: 'Reservation' = None


class UpdateRoomClose(ServiceBase, HouseSelectMixin, RoomSelectMixin, ReservationSelectMixin):
    @inject.autoparams()
    def __init__(
        self,
        houses_repo: HousesRepo,
        rooms_repo: RoomsRepo,
        reservations_repo: ReservationsRepo,
        changelog_repo: ChangelogRepo,
    ):
        self._houses_repo = houses_repo
        self._rooms_repo = rooms_repo
        self._reservations_repo = reservations_repo
        self._changelog_repo = changelog_repo

        self._case_errors = ReservationErrors

    def execute(
        self,
        pk: str,
        house_id: int,
        room_id: int,
        start_date: datetime.date,
        end_date: datetime.date,
        reason: RoomCloseReasons,
        user: 'User',
        notes: str = '',
    ) -> ResultE[ReservationUpdateContext]:
        pk = cf.get_int_or_none((pk or '').split('-')[0]) or 0
        ctx = Context(
            pk=pk,
            house_id=house_id,
            room_id=room_id,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
            user=user,
            notes=notes,
        )
        return flow(
            ctx,
            self.select_house,
            bind_result(self.select_room),
            bind_result(self.select_reservation),
            bind_result(self.check_room_is_free),
            bind_result(self.make_reservation_from_data),
            bind_result(self.save_reservation),
            bind_result(self.accept_reservation),
            bind_result(self.write_changelog),
            bind_result(self.make_result),
        )

    def accept_reservation(self, ctx: Context) -> ResultE[Context]:
        try:
            data = self._reservations_repo.accept(ctx.reservation.id)
            if data == Nothing:
                return self._error(
                    f"Error accept Reservation ID={ctx.reservation.id} in House ID={ctx.house.id}",
                    ctx,
                    self._case_errors.save,
                )
            ctx.reservation = data.unwrap()
            return Success(ctx)
        except Exception as err:
            return self._error(
                f"Error accept Reservation ID={ctx.reservation.id} in House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )

    def check_reservation(self, ctx: Context) -> ResultE[Context]:
        if ctx.source.house_id != ctx.house.id:
            return self._error(
                f"Reservation ID={ctx.source.id} has House ID={ctx.source.house_id} "
                f"but heeds to be House ID={ctx.house.id}",
                ctx,
                self._case_errors.missed_reservation,
            )
        if ctx.source.status != ReservationStatuses.CLOSE:
            return self._error(
                f"Reservation ID={ctx.source.id} has wrong status", ctx, self._case_errors.missed_reservation
            )
        return Success(ctx)

    def check_room_is_free(self, ctx: Context) -> ResultE[Context]:
        reservation_rooms = [x.id for x in ctx.source.rooms]
        try:
            data = self._reservations_repo.is_room_busy(
                ctx.room.id, ctx.start_date, ctx.end_date, exclude_rooms=reservation_rooms
            )
            if data:
                return self._error(
                    f"Room ID={ctx.room.id} is busy for {ctx.start_date}..{ctx.end_date}",
                    ctx,
                    self._case_errors.busy_room,
                )
            return Success(ctx)
        except Exception as err:
            return self._error(
                f"Error check if Room ID={ctx.room.id} is busy for period {ctx.start_date}..{ctx.end_date}",
                ctx,
                self._case_errors.error,
                exc=err,
            )

    @staticmethod
    def make_reservation_from_data(ctx: Context) -> ResultE[Context]:
        rooms = []
        for room in ctx.source.rooms:
            source_prices = {x.day: x for x in room.day_prices}
            prices = []
            for day in cf.get_days_for_period(ctx.start_date, ctx.end_date, exclude=True):
                if day in source_prices:
                    prices.append(
                        attr.evolve(source_prices[day], roomtype_id=ctx.room.roomtype_id, room_id=ctx.room.id)
                    )
                else:
                    prices.append(
                        ReservationDay(
                            id=None,
                            reservation_room_id=room.id,
                            day=day,
                            roomtype_id=ctx.room.roomtype_id,
                            room_id=ctx.room.id,
                        )
                    )
            rooms.append(
                attr.evolve(
                    room, checkin=ctx.start_date, checkout=ctx.end_date, notes_info=ctx.notes, day_prices=prices
                )
            )
        ctx.reservation = attr.evolve(
            ctx.source, checkin=ctx.start_date, checkout=ctx.end_date, close_reason=ctx.reason, rooms=rooms
        )
        return Success(ctx)

    @staticmethod
    def make_result(ctx: Context) -> ResultE[ReservationUpdateContext]:
        return Success(
            ReservationUpdateContext(
                reservation=ctx.reservation,
                start_date=min(ctx.source.checkin, ctx.reservation.checkin),
                end_date=max(ctx.source.checkout, ctx.reservation.checkout),
            )
        )

    def save_reservation(self, ctx: Context) -> ResultE[Context]:
        try:
            data, __ = self._reservations_repo.save(ctx.reservation)
            if data == Nothing:
                return self._error(
                    f"Error save Reservation ID={ctx.reservation.id} in House ID={ctx.house.id}",
                    ctx,
                    self._case_errors.save,
                )
            ctx.reservation = data.unwrap()
            return Success(ctx)
        except Exception as err:
            return self._error(
                f"Error save Reservation ID={ctx.reservation.id} in House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )

    def write_changelog(self, ctx: Context) -> ResultE[Context]:
        try:
            changes = {}
            if ctx.source.checkin != ctx.reservation.checkin:
                changes['checkin'] = (
                    ctx.source.checkin.strftime('%d/%m/%Y'),
                    ctx.reservation.checkin.strftime('%d/%m/%Y'),
                )
            if ctx.source.checkout != ctx.reservation.checkout:
                changes['checkout'] = (
                    ctx.source.checkout.strftime('%d/%m/%Y'),
                    ctx.reservation.checkout.strftime('%d/%m/%Y'),
                )
            if ctx.source.close_reason != ctx.reservation.close_reason:
                changes['close_reason'] = (
                    ctx.source.close_reason.value if ctx.source.close_reason is not None else None,
                    ctx.reservation.close_reason.value if ctx.reservation.close_reason is not None else None,
                )
            try:
                if ctx.source.rooms[0].notes_info != ctx.reservation.rooms[0].notes_info:
                    changes['notes'] = (ctx.source.rooms[0].notes_info, ctx.reservation.rooms[0].notes_info)
            except IndexError:
                pass
            self._changelog_repo.create_manual(
                ctx.user,
                ctx.reservation,
                ChangelogActions.UPDATE,
                changes=changes,
                house=ctx.house,
                message=(
                    f"Update Room [{ctx.room.name}] closing "
                    f"for {ctx.start_date.isoformat()}..{ctx.end_date.isoformat()}"
                ),
            )
        except Exception as err:
            Logger.warning(__name__, f"Error write changelog: {err}")
        return Success(ctx)
