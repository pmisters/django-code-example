import dataclasses
import datetime
from typing import TYPE_CHECKING

import inject
from returns.maybe import Nothing
from returns.pipeline import flow
from returns.pointfree import bind_result
from returns.result import Success

from action_logger.repositories import ChangelogRepo
from board.repositories import ReservationsCacheRepo, ReservationsRepo
from board.value_objects import ReservationErrors
from common import functions as cf
from common.loggers import Logger
from common.mixins import HouseSelectMixin
from common.value_objects import ResultE, ServiceBase
from effective_tours.constants import ChangelogActions, ReservationStatuses
from houses.repositories import HousesRepo, RoomTypesRepo, RoomsRepo

if TYPE_CHECKING:
    from board.entities import Reservation
    from houses.entities import House, Room, RoomType
    from members.entities import User


@dataclasses.dataclass
class Context:
    pk: str
    reservation_id: int
    house_id: int
    roomtype_id: int = None
    room_id: int = None
    user: 'User' = None
    house: 'House' = None
    room_type: 'RoomType' = None
    room: "Room" = None
    start_date: datetime.date = None
    end_date: datetime.date = None
    reservation: 'Reservation' = None


class MoveReservation(ServiceBase, HouseSelectMixin):
    @inject.autoparams()
    def __init__(
        self,
        houses_repo: HousesRepo,
        cache_repo: ReservationsCacheRepo,
        reservations_repo: ReservationsRepo,
        roomtypes_repo: RoomTypesRepo,
        rooms_repo: RoomsRepo,
        changelog_repo: ChangelogRepo,
    ):
        self._houses_repo = houses_repo
        self._rooms_repo = rooms_repo
        self._roomtypes_repo = roomtypes_repo
        self._cache_repo = cache_repo
        self._reservations_repo = reservations_repo
        self._changelog_repo = changelog_repo

        self._case_errors = ReservationErrors

    def execute(
        self,
        pk: str,
        reservation_id: int,
        house_id: int,
        roomtype_id: int = None,
        room_id: int = None,
        user: 'User' = None,
    ) -> ResultE[None]:
        ctx = Context(
            pk=pk,
            reservation_id=reservation_id,
            house_id=house_id,
            roomtype_id=roomtype_id,
            room_id=room_id,
            user=user,
        )
        return flow(
            ctx,
            self.select_house,
            bind_result(self.select_reservation_from_cache),
            bind_result(self.select_reservation_from_db),
            bind_result(self.select_room_type),
            bind_result(self.select_room),
            bind_result(self.update_reservation),
            bind_result(self.save),
            bind_result(self.write_changelog),
            bind_result(lambda x: Success(None)),
        )

    def save(self, ctx: Context) -> ResultE[Context]:
        try:
            data, __ = self._reservations_repo.save(ctx.reservation)
        except Exception as err:
            return self._error(
                f"Error save Reservation ID={ctx.reservation.id}", ctx, self._case_errors.error, exc=err
            )
        if data == Nothing:
            return self._error(f"Error save Reservation ID={ctx.reservation.id}", ctx, self._case_errors.error)
        ctx.reservation = data.unwrap()
        return Success(ctx)

    def select_reservation_from_cache(self, ctx: Context) -> ResultE[Context]:
        pk = (ctx.pk or '').strip()
        if pk == '' or '-' not in pk:
            return self._error('Missed Reservation Part ID', ctx, self._case_errors.missed_reservation)
        try:
            data = self._cache_repo.get(ctx.house.id, pk)
        except Exception as err:
            return self._error(f"Error select Reservation ID={pk} from Cache", ctx, self._case_errors.error, exc=err)
        if data == Nothing:
            return self._error(f"Missed Reservation ID={pk} in Cache", ctx, self._case_errors.missed_reservation)
        reservation = data.unwrap()
        ctx.start_date = reservation.checkin.date()
        ctx.end_date = reservation.checkout.date() - datetime.timedelta(days=1)
        return Success(ctx)

    def select_reservation_from_db(self, ctx: Context) -> ResultE[Context]:
        pk = cf.get_int_or_none(ctx.reservation_id) or 0
        if pk <= 0:
            return self._error('Missed Reservation ID', ctx, self._case_errors.missed_reservation)
        try:
            data = self._reservations_repo.get(pk)
        except Exception as err:
            return self._error(f"Error select Reservation ID={pk}", ctx, self._case_errors.error, exc=err)
        if data == Nothing:
            return self._error(f"Unknown Reservation ID={pk}", ctx, self._case_errors.missed_reservation)
        ctx.reservation = data.unwrap()
        if ctx.reservation.status == ReservationStatuses.CANCEL:
            return self._error(f"Reservation ID={pk} is cancelled", ctx, self._case_errors.missed_reservation)
        return Success(ctx)

    def select_room(self, ctx: Context) -> ResultE[Context]:
        if ctx.room_id is None:
            return Success(ctx)
        pk = cf.get_int_or_none(ctx.room_id) or 0
        if pk <= 0:
            return self._error('Wrong Room ID', ctx, self._case_errors.missed_room)
        try:
            data = self._rooms_repo.get(pk)
        except Exception as err:
            return self._error(
                f"Error select Room ID={pk} in House ID={ctx.house.id}", ctx, self._case_errors.error, exc=err
            )
        if data == Nothing:
            return self._error(
                f"Unknown Room ID={pk} in House ID={ctx.house.id}", ctx, self._case_errors.missed_room
            )
        ctx.room = data.unwrap()
        return Success(ctx)

    def select_room_type(self, ctx: Context) -> ResultE[Context]:
        if ctx.roomtype_id is None:
            return Success(ctx)
        pk = cf.get_int_or_none(ctx.roomtype_id) or 0
        if pk <= 0:
            return self._error('Wrong Room Type ID', ctx, self._case_errors.missed_roomtype)
        try:
            data = self._roomtypes_repo.get(ctx.house, pk=pk, user=ctx.user)
        except Exception as err:
            return self._error(
                f"Error select Room Type ID={pk} in House ID={ctx.house.id}", ctx, self._case_errors.error, exc=err
            )
        if data == Nothing:
            return self._error(
                f"Unknown Room Type ID={pk} in House ID={ctx.house.id}", ctx, self._case_errors.missed_roomtype
            )
        ctx.room_type = data.unwrap()
        return Success(ctx)

    def update_reservation(self, ctx: Context) -> ResultE[Context]:
        if ctx.room_type is None and ctx.room is None:
            return self._error('Nothing to update: no destination Room/RoomType', ctx, self._case_errors.error)
        for room in ctx.reservation.rooms:
            if not ctx.pk.startswith(f"{ctx.reservation.id}-{room.id}-"):
                continue
            for price in room.day_prices:
                if ctx.start_date <= price.day <= ctx.end_date:
                    if ctx.room_type is not None:
                        price.roomtype_id = ctx.room_type.id
                        price.room_id = None
                    elif ctx.room is not None:
                        price.room_id = ctx.room.id
                        price.roomtype_id = ctx.room.roomtype_id
        return Success(ctx)

    def write_changelog(self, ctx: Context) -> ResultE[Context]:
        try:
            destination = ''
            if ctx.room_type is not None:
                destination = ctx.room_type.name
            elif ctx.room is not None:
                destination = ctx.room.name
            self._changelog_repo.create_manual(
                ctx.user,
                ctx.reservation,
                ChangelogActions.UPDATE,
                {},
                house=ctx.house,
                message=(
                    f"Move Reservation {ctx.reservation.get_id()} "
                    f"[{ctx.start_date.isoformat()}..{ctx.end_date.isoformat()}] to {destination}"
                ),
            )
        except Exception as err:
            Logger.warning(__name__, f"Error write changelog : {err}")
        return Success(ctx)
