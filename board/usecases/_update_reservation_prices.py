import dataclasses
import datetime
from decimal import Decimal
from typing import Any, Dict, TYPE_CHECKING, Optional

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
from board.value_objects import ReservationErrors
from cancelations.repositories import PoliciesRepo
from common import functions as cf
from common.loggers import Logger
from common.mixins import HouseSelectMixin, RatePlanSelectMixin
from common.value_objects import ResultE, ServiceBase
from effective_tours.constants import ChangelogActions
from house_prices.repositories import PricesRepo
from houses.repositories import HousesRepo, RoomTypesRepo, RoomsRepo

if TYPE_CHECKING:
    from board.entities import Reservation, ReservationRoom
    from house_prices.entities import RatePlan
    from houses.entities import House, Room, RoomType
    from members.entities import User


@dataclasses.dataclass
class Context:
    house_id: int
    pk: int
    room_id: int
    plan_id: int
    user: 'User'
    prices: Dict[datetime.date, Dict[str, Any]] = None
    house: 'House' = None
    source: 'Reservation' = None
    reservation: 'Reservation' = None
    reservation_room: 'ReservationRoom' = None
    rate_plan: 'RatePlan' = None
    room_types: Dict[int, 'RoomType'] = dataclasses.field(default_factory=dict)
    rooms: Dict[int, 'Room'] = dataclasses.field(default_factory=dict)


class UpdateReservationPrices(ServiceBase, HouseSelectMixin, RatePlanSelectMixin, ReservationSelectMixin):
    @inject.autoparams()
    def __init__(
        self,
        houses_repo: HousesRepo,
        reservations_repo: ReservationsRepo,
        prices_repo: PricesRepo,
        roomtypes_repo: RoomTypesRepo,
        rooms_repo: RoomsRepo,
        policies_repo: PoliciesRepo,
        changelog_repo: ChangelogRepo,
    ):
        self._houses_repo = houses_repo
        self._reservations_repo = reservations_repo
        self._prices_repo = prices_repo
        self._roomtypes_repo = roomtypes_repo
        self._rooms_repo = rooms_repo
        self._policies_repo = policies_repo
        self._changelog_repo = changelog_repo

        self._case_errors = ReservationErrors

    def execute(
        self,
        house_id: int,
        pk: int,
        room_id: int,
        plan_id: int,
        user: 'User',
        prices: Dict[datetime.date, Dict[str, Any]] = None,
    ) -> ResultE['Reservation']:
        ctx = Context(house_id=house_id, pk=pk, room_id=room_id, user=user, plan_id=plan_id, prices=prices)
        return flow(
            ctx,
            self.select_house,
            bind_result(self.select_reservation),
            bind_result(self.check_reservation),
            bind_result(self.select_reservation_room),
            bind_result(self.is_allow_update_period),
            bind_result(self.select_rate_plan),
            bind_result(self.select_cancellation_policy),
            bind_result(self.select_room_types),
            bind_result(self.select_rooms),
            bind_result(self.make_reservation_from_data),
            bind_result(self.save_reservation),
            bind_result(self.write_changelog),
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
        if not ctx.source.allow_update_prices():
            return self._error(
                f"Reservation ID={ctx.source.id} is not allowed to update prices",
                ctx,
                self._case_errors.missed_reservation,
            )
        return Success(ctx)

    def is_allow_update_period(self, ctx: Context) -> ResultE[Context]:
        if not ctx.source.is_ota():
            return Success(ctx)
        if (
            min(ctx.prices.keys()) != ctx.reservation_room.checkin
            or max(ctx.prices.keys()) != ctx.reservation_room.checkout - datetime.timedelta(days=1)
        ):
            return self._error(
                f"Period change not allowed for OTA Reservation ID={ctx.source.id}",
                ctx,
                self._case_errors.wrong_period,
            )
        return Success(ctx)

    def make_reservation_from_data(self, ctx: Context) -> ResultE[Context]:
        ctx.reservation = attr.evolve(ctx.source, rooms=[])

        for room in ctx.source.rooms:
            if room.id != ctx.reservation_room.id:
                # Other rooms copy without changes
                ctx.reservation.rooms.append(room)
                continue

            # Update selected room
            _room = attr.evolve(room, day_prices=[])
            if _room.rate_plan_id != ctx.rate_plan.id:
                _room.rate_plan_id = ctx.rate_plan.id
                _room.policy = ctx.rate_plan.policy.dump() if ctx.rate_plan.policy is not None else {}

            # Get one of used Room Types than will be used for new day prices
            failback_roomtype_id = self._room_type_for_failback(room)

            # Update daily prices
            day_prices = {x.day: x for x in room.day_prices}
            for day, data in ctx.prices.items():
                # Set price
                new_price = cf.get_decimal_or_none(data.get('price')) or Decimal(0)
                if day in day_prices:
                    _price = attr.evolve(day_prices[day])
                else:
                    _price = ReservationDay(id=None, reservation_room_id=_room.id, day=day, price_changed=new_price)
                _price.price_accepted = new_price
                _price.tax = _price.price_accepted * ctx.house.tax / Decimal(100)

                # Set room
                new_room = ctx.rooms.get(cf.get_int_or_none(data.get('room')) or 0)
                _price.room_id = new_room.id if new_room is not None else None
                if new_room is not None and new_room.roomtype_id in ctx.room_types:
                    _price.roomtype_id = new_room.roomtype_id
                if _price.roomtype_id is None or _price.roomtype_id <= 0:
                    _price.roomtype_id = failback_roomtype_id

                _room.day_prices.append(_price)

            # Recalculate room prices
            _room.netto_price_accepted = sum([x.price_accepted for x in _room.day_prices])
            _room.tax = sum([x.tax for x in _room.day_prices])
            _room.price_accepted = _room.netto_price_accepted + _room.tax
            _room.checkin = min([x.day for x in _room.day_prices])
            _room.checkout = max([x.day for x in _room.day_prices]) + datetime.timedelta(days=1)  # checkout next day

            ctx.reservation.rooms.append(_room)

        # Recalculate reservation total prices
        ctx.reservation.netto_price_accepted = sum([x.netto_price_accepted for x in ctx.reservation.rooms])
        ctx.reservation.price_accepted = sum([x.price_accepted for x in ctx.reservation.rooms])
        ctx.reservation.tax = sum([x.tax for x in ctx.reservation.rooms])
        ctx.reservation.checkin = min([x.checkin for x in ctx.reservation.rooms])
        ctx.reservation.checkout = max([x.checkout for x in ctx.reservation.rooms])

        return Success(ctx)

    def save_reservation(self, ctx: Context) -> ResultE[Context]:
        try:
            data, __ = self._reservations_repo.save(ctx.reservation, with_accepted_prices=True)
        except Exception as err:
            return self._error(
                f"Error save Reservation ID={ctx.reservation.id} for House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        if data == Nothing:
            return self._error(
                f"Error save prices for Reservation ID={ctx.reservation.id} for House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
            )
        ctx.reservation = data.unwrap()
        return Success(ctx)

    def select_cancellation_policy(self, ctx: Context) -> ResultE[Context]:
        if ctx.reservation_room.rate_plan_id == ctx.rate_plan.id:
            return Success(ctx)
        if ctx.rate_plan.policy_id is None or ctx.rate_plan.policy_id <= 0:
            return Success(ctx)
        try:
            data = self._policies_repo.get(ctx.house.id, ctx.rate_plan.policy_id, detailed=True)
        except Exception as err:
            return self._error(
                f"Error select Cancellation Policy ID={ctx.rate_plan.policy_id} for House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        if data != Nothing:
            ctx.rate_plan.policy = data.unwrap()
        return Success(ctx)

    def select_reservation_room(self, ctx: Context) -> ResultE[Context]:
        pk = cf.get_int_or_none(ctx.room_id) or 0
        if pk <= 0:
            return self._error('Missed Reservation Room ID', ctx, self._case_errors.missed_reservation)
        rooms = {x.id: x for x in ctx.source.rooms}
        if pk not in rooms:
            return self._error(
                f"Unknown Room ID={pk} in Reservation ID={ctx.source.id} House ID={ctx.house.id}",
                ctx,
                self._case_errors.missed_reservation,
            )
        ctx.reservation_room = rooms[pk]
        return Success(ctx)

    def select_room_types(self, ctx: Context) -> ResultE[Context]:
        try:
            data = self._roomtypes_repo.select(ctx.house, user=ctx.user, detailed=False)
        except Exception as err:
            return self._error(
                f"Error select Room Types for House ID={ctx.house.id}", ctx, self._case_errors.error, exc=err
            )
        ctx.room_types = {x.id: x for x in data}
        return Success(ctx)

    def select_rooms(self, ctx: Context) -> ResultE[Context]:
        try:
            data = self._rooms_repo.select(ctx.house.id)
        except Exception as err:
            return self._error(
                f"Error select Rooms for House ID={ctx.house.id}", ctx, self._case_errors.error, exc=err
            )
        ctx.rooms = {x.id: x for x in data}
        return Success(ctx)

    def write_changelog(self, ctx: Context) -> ResultE[Context]:
        try:
            self._changelog_repo.create_manual(
                ctx.user,
                ctx.reservation,
                ChangelogActions.UPDATE,
                {},
                house=ctx.house,
                message=f"Update prices for Reservation {ctx.reservation.get_id_for_log()}",
            )
        except Exception as err:
            Logger.warning(__name__, f"Error write changelog: {err}")
        return Success(ctx)

    @staticmethod
    def _room_type_for_failback(reservation_room: 'ReservationRoom') -> Optional[int]:
        for price in reservation_room.day_prices:
            if price.roomtype_id is not None and price.roomtype_id > 0:
                return price.roomtype_id
        return None
