import dataclasses
import datetime
from typing import TYPE_CHECKING

import inject
from django.utils import timezone
from returns.maybe import Nothing
from returns.pipeline import flow
from returns.pointfree import bind_result
from returns.result import Success

from action_logger.repositories import ChangelogRepo
from board.entities import Reservation, ReservationDay, ReservationRoom
from board.repositories import ReservationsRepo
from board.value_objects import ReservationErrors
from common import functions as cf
from common.loggers import Logger
from common.mixins import HouseSelectMixin, RoomSelectMixin
from common.value_objects import ResultE, ServiceBase
from effective_tours.constants import ChangelogActions, ReservationSources, ReservationStatuses, RoomCloseReasons
from houses.repositories import HousesRepo, RoomsRepo

if TYPE_CHECKING:
    from houses.entities import House, Room
    from members.entities import User


@dataclasses.dataclass
class Context:
    house_id: int
    room_id: int
    start_date: datetime.date
    end_date: datetime.date
    reason: RoomCloseReasons
    user: 'User'
    notes: str = ''
    house: "House" = None
    room: "Room" = None
    reservation: Reservation = None


class CreateRoomClose(ServiceBase, HouseSelectMixin, RoomSelectMixin):
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
        house_id: int,
        room_id: int,
        start_date: datetime.date,
        end_date: datetime.date,
        reason: RoomCloseReasons,
        user: 'User',
        notes: str = '',
    ) -> ResultE[Reservation]:
        ctx = Context(
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
            bind_result(self.check_room_is_free),
            bind_result(self.make_reservation_from_date),
            bind_result(self.save_reservation),
            bind_result(self.accept_reservation),
            bind_result(self.write_changelog),
            bind_result(lambda x: Success(x.reservation)),
        )

    def accept_reservation(self, ctx: Context) -> ResultE[Context]:
        try:
            data = self._reservations_repo.accept(ctx.reservation.id)
            if data == Nothing:
                return self._error(
                    f"Error accept new Reservation for Room ID={ctx.room.id} in House ID={ctx.house.id}",
                    ctx,
                    self._case_errors.save,
                )
            ctx.reservation = data.unwrap()
            return Success(ctx)
        except Exception as err:
            return self._error(
                f"Error accept new Reservation for Room ID={ctx.room.id} in House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )

    def check_room_is_free(self, ctx: Context) -> ResultE[Context]:
        try:
            data = self._reservations_repo.is_room_busy(ctx.room.id, ctx.start_date, ctx.end_date)
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
    def make_reservation_from_date(ctx: Context) -> ResultE[Context]:
        ctx.reservation = Reservation(
            id=None,
            house_id=ctx.house.id,
            connection_id=None,
            source=ReservationSources.MANUAL,
            channel=None,
            channel_id='',
            checkin=ctx.start_date,
            checkout=ctx.end_date,
            booked_at=timezone.now(),
            status=ReservationStatuses.CLOSE,
            close_reason=ctx.reason,
            room_count=1,
            currency=ctx.house.currency.code if ctx.house.currency is not None else None,
            is_verified=True,
            verified_at=timezone.now(),
        )
        ctx.reservation.rooms.append(
            ReservationRoom(
                id=None,
                reservation_id=None,
                channel_id='',
                channel_rate_id='',
                checkin=ctx.start_date,
                checkout=ctx.end_date,
                currency=ctx.house.currency.code if ctx.house.currency is not None else None,
                notes_info=ctx.notes,
            )
        )
        for day in cf.get_days_for_period(ctx.start_date, ctx.end_date, exclude=True):
            ctx.reservation.rooms[0].day_prices.append(
                ReservationDay(
                    id=None,
                    reservation_room_id=None,
                    day=day,
                    roomtype_id=ctx.room.roomtype_id,
                    room_id=ctx.room.id,
                    currency=ctx.house.currency.code if ctx.house.currency is not None else None,
                )
            )
        return Success(ctx)

    def save_reservation(self, ctx: Context) -> ResultE[Context]:
        try:
            data, __ = self._reservations_repo.save(ctx.reservation)
            if data == Nothing:
                return self._error(
                    f"Error save Reservation for Room ID={ctx.room.id} in House ID={ctx.house.id}",
                    ctx,
                    self._case_errors.save,
                )
            ctx.reservation = data.unwrap()
            return Success(ctx)
        except Exception as err:
            return self._error(
                f"Error save Reservation for Room ID={ctx.room.id} in House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )

    def write_changelog(self, ctx: Context) -> ResultE[Context]:
        try:
            self._changelog_repo.create_manual(
                ctx.user,
                ctx.reservation,
                ChangelogActions.CREATE,
                {},
                house=ctx.house,
                message=f"Close Room [{ctx.room.name}] for {ctx.start_date.isoformat()}..{ctx.end_date.isoformat()}",
            )
        except Exception as err:
            Logger.warning(__name__, f"Error write changelog: {err}")
        return Success(ctx)
