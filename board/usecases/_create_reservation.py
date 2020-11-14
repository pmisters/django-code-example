import dataclasses
from decimal import Decimal
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
from board.value_objects import ReservationErrors, ReservationRequest
from cancelations.repositories import PoliciesRepo
from common import functions as cf
from common.loggers import Logger
from common.mixins import HouseSelectMixin
from common.value_objects import ResultE, ServiceBase
from effective_tours.constants import ChangelogActions, ReservationSources, ReservationStatuses
from house_prices.entities import Rate
from house_prices.repositories import PricesRepo
from houses.repositories import HousesRepo, RoomTypesRepo

if TYPE_CHECKING:
    from house_prices.entities import RatePlan
    from houses.entities import House, RoomType
    from members.entities import User


@dataclasses.dataclass
class Context:
    house_id: int
    request: ReservationRequest
    user: 'User'
    house: 'House' = None
    room_type: 'RoomType' = None
    rate_plan: 'RatePlan' = None
    rate: Rate = None
    reservation: Reservation = None


class CreateReservation(ServiceBase, HouseSelectMixin):
    @inject.autoparams()
    def __init__(
        self,
        houses_repo: HousesRepo,
        roomtypes_repo: RoomTypesRepo,
        prices_repo: PricesRepo,
        reservations_repo: ReservationsRepo,
        policies_repo: PoliciesRepo,
        changelog_repo: ChangelogRepo,
    ):
        self._houses_repo = houses_repo
        self._roomtypes_repo = roomtypes_repo
        self._prices_repo = prices_repo
        self._policies_repo = policies_repo
        self._reservations_repo = reservations_repo
        self._changelog_repo = changelog_repo

        self._case_errors = ReservationErrors

    def execute(self, house_id: int, request: ReservationRequest, user: 'User') -> ResultE[Reservation]:
        ctx = Context(house_id=house_id, request=request, user=user)
        if not isinstance(ctx.request, ReservationRequest):
            return self._error('Missed Reservation data', ctx, self._case_errors.missed_reservation)

        return flow(
            ctx,
            self.select_house,
            bind_result(self.select_room_type),
            bind_result(self.select_rate_plan),
            bind_result(self.select_rate),
            bind_result(self.select_cancellation_policy),
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
                    f"Error accept new Reservation for Room Type ID={ctx.room_type.id} in House ID={ctx.house.id}",
                    ctx,
                    self._case_errors.save,
                )
        except Exception as err:
            return self._error(
                f"Error accept new Reservation for Room Type ID={ctx.room_type.id} in House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        ctx.reservation = data.unwrap()
        return Success(ctx)

    @staticmethod
    def make_reservation_from_date(ctx: Context) -> ResultE[Context]:
        netto_price = sum(ctx.request.prices.values()) if ctx.request.prices else Decimal(0)
        taxes = netto_price * ctx.house.tax / Decimal(100) if ctx.house.tax > Decimal(0) else Decimal(0)
        price = netto_price + taxes

        ctx.reservation = Reservation(
            id=None,
            house_id=ctx.house.id,
            connection_id=None,
            source=ReservationSources.MANUAL,
            channel=None,
            channel_id='',
            checkin=ctx.request.checkin,
            checkout=ctx.request.checkout,
            booked_at=timezone.now(),
            status=ReservationStatuses.HOLD,
            room_count=1,
            currency=ctx.house.currency.code if ctx.house.currency is not None else None,
            price=price,
            netto_price=netto_price,
            tax=taxes,
            guest_name=ctx.request.guest_name,
            guest_surname=ctx.request.guest_surname,
            guest_email=ctx.request.guest_email,
            guest_phone=ctx.request.guest_phone,
            is_verified=True,
            verified_at=timezone.now(),
        )
        ctx.reservation.rooms.append(
            ReservationRoom(
                id=None,
                reservation_id=None,
                channel_id='',
                channel_rate_id='',
                checkin=ctx.request.checkin,
                checkout=ctx.request.checkout,
                rate_plan_id=ctx.rate_plan.id,
                rate_id=ctx.rate.id if ctx.rate is not None else None,
                guest_name=' '.join([ctx.request.guest_name, ctx.request.guest_surname]).strip(),
                guest_count=ctx.request.guests,
                adults=ctx.request.guests,
                currency=ctx.house.currency.code if ctx.house.currency is not None else None,
                price=ctx.reservation.price,
                netto_price=ctx.reservation.netto_price,
                tax=ctx.reservation.tax,
                notes_info=ctx.request.notes,
                policy=ctx.rate_plan.policy.dump() if ctx.rate_plan.policy is not None else {},
            )
        )
        for day in cf.get_days_for_period(ctx.request.checkin, ctx.request.checkout, exclude=True):
            day_price = ctx.request.prices.get(day) or Decimal(0)
            taxes = day_price * ctx.house.tax / Decimal(100) if ctx.house.tax > Decimal(0) else Decimal(0)
            ctx.reservation.rooms[0].day_prices.append(
                ReservationDay(
                    id=None,
                    reservation_room_id=None,
                    day=day,
                    roomtype_id=ctx.room_type.id,
                    price_changed=day_price,
                    price_original=day_price,
                    price_accepted=day_price,
                    tax=taxes,
                    currency=ctx.house.currency.code if ctx.house.currency is not None else None,
                )
            )
        return Success(ctx)

    def save_reservation(self, ctx: Context) -> ResultE[Context]:
        try:
            data, __ = self._reservations_repo.save(ctx.reservation)
            if data == Nothing:
                return self._error(
                    f"Error save Reservation for Room Type ID={ctx.room_type.id} in House ID={ctx.house.id}",
                    ctx,
                    self._case_errors.save,
                )
        except Exception as err:
            return self._error(
                f"Error save Reservation for Room Type ID={ctx.room_type.id} in House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        ctx.reservation = data.unwrap()
        return Success(ctx)

    def select_cancellation_policy(self, ctx: Context) -> ResultE[Context]:
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

    def select_rate(self, ctx: Context) -> ResultE[Context]:
        pk = cf.get_int_or_none(ctx.request.rate_id) or 0
        if pk <= 0:
            return self._error('Missed Rate ID', ctx, self._case_errors.missed_rate)
        try:
            rates = self._prices_repo.select_rates(
                ctx.house, room_type=ctx.room_type, plan_id=ctx.rate_plan.id, user=ctx.user
            )
        except Exception as err:
            return self._error(
                f"Error select Rates for Room Type ID={ctx.room_type.id} in House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        rates = [x for x in rates if x.id == pk]
        if not rates:
            return self._error(
                f"Unknown Rate ID={pk} for Room Type ID={ctx.room_type.id} in House ID={ctx.house.id}",
                ctx,
                self._case_errors.missed_rate,
            )
        ctx.rate = rates[0]
        return Success(ctx)

    def select_rate_plan(self, ctx: Context) -> ResultE[Context]:
        pk = cf.get_int_or_none(ctx.request.plan_id) or 0
        if pk <= 0:
            return self._error('Missed Rate Plan ID', ctx, self._case_errors.missed_rateplan)
        try:
            data = self._prices_repo.get_plan(ctx.house.odoo_id, pk, user=ctx.user)
            if data == Nothing:
                return self._error(
                    f"Unknown Rate Plan ID={pk} in House ID={ctx.house.id}", ctx, self._case_errors.missed_rateplan
                )
        except Exception as err:
            return self._error(
                f"Error select Rate Plan ID={pk} in House ID={ctx.house.id}", ctx, self._case_errors.error, exc=err
            )
        ctx.rate_plan = data.unwrap()
        return Success(ctx)

    def select_room_type(self, ctx: Context) -> ResultE[Context]:
        pk = cf.get_int_or_none(ctx.request.roomtype_id) or 0
        if pk <= 0:
            return self._error('Missed Room Type ID', ctx, self._case_errors.missed_roomtype)
        try:
            data = self._roomtypes_repo.get(ctx.house, pk=pk, user=ctx.user)
            if data == Nothing:
                return self._error(
                    f"Unknown Room Type ID={pk} in House ID={ctx.house.id}", ctx, self._case_errors.missed_roomtype
                )
        except Exception as err:
            return self._error(
                f"Error select Room Type ID={pk} in House ID={ctx.house.id}", ctx, self._case_errors.error, exc=err
            )
        ctx.room_type = data.unwrap()
        return Success(ctx)

    def write_changelog(self, ctx: Context) -> ResultE[Context]:
        try:
            self._changelog_repo.create(
                ctx.user,
                None,
                ctx.reservation,
                ChangelogActions.CREATE,
                house=ctx.house,
                message='Create a new Reservation',
            )
        except Exception as err:
            Logger.warning(__name__, f"Error write changelog: {err}")
        return Success(ctx)
