import dataclasses
import datetime
from decimal import Decimal
from typing import Any, Dict, List, TYPE_CHECKING

import inject
from returns.maybe import Nothing
from returns.pipeline import flow
from returns.pointfree import bind_result
from returns.result import Success

from board.repositories import ReservationsCacheRepo, ReservationsRepo
from board.value_objects import CachedReservation, ReservationErrors
from common import functions as cf
from common.mixins import HouseSelectMixin, OdooApiMixin
from common.value_objects import ResultE, ServiceBase
from effective_tours.constants import (
    DEFAULT_CHECKIN_TIME, DEFAULT_CHECKOUT_TIME, ReservationSources, ReservationStatuses
)
from house_prices.repositories import PricesRepo
from houses.repositories import HousesRepo
from members.repositories import MembersRepo

if TYPE_CHECKING:
    from board.entities import Reservation, ReservationRoom
    from house_prices.entities import RatePlan
    from houses.entities import House
    from ledger.entities import Currency
    from members.entities import User
    from odoo import OdooRPCAPI


@dataclasses.dataclass
class Context:
    house_id: int
    pk: int = None
    start_date: datetime.date = None
    end_date: datetime.date = None
    house: 'House' = None
    user: 'User' = None
    payed_amounts: Dict[int, Decimal] = dataclasses.field(default_factory=dict)
    reservations: List['Reservation'] = dataclasses.field(default_factory=list)
    rate_plans: Dict[int, 'RatePlan'] = dataclasses.field(default_factory=dict)
    cached_reservations: List[CachedReservation] = dataclasses.field(default_factory=list)
    api: 'OdooRPCAPI' = None


class UpdateReservationCache(HouseSelectMixin, OdooApiMixin, ServiceBase):
    @inject.autoparams()
    def __init__(
        self,
        houses_repo: HousesRepo,
        reservations_repo: ReservationsRepo,
        prices_repo: PricesRepo,
        cache_repo: ReservationsCacheRepo,
        members_repo: MembersRepo,
    ):
        self._houses_repo = houses_repo
        self._reservations_repo = reservations_repo
        self._prices_repo = prices_repo
        self._cache_repo = cache_repo
        self._members_repo = members_repo

        self._case_errors = ReservationErrors

    def execute(
        self, house_id: int, pk: int = None, start_date: datetime.date = None, end_date: datetime.date = None
    ) -> ResultE[None]:
        ctx = Context(house_id=house_id, pk=pk, start_date=start_date, end_date=end_date)
        return flow(
            ctx,
            self.select_house,
            bind_result(self.select_reservations),
            bind_result(self.select_bot_user),
            bind_result(self.select_rate_plans),
            bind_result(self.select_payed_amounts),
            bind_result(self.process_reservations),
            bind_result(self.remove_canceled_reservations),
            bind_result(self.save_cache),
            bind_result(lambda x: Success(None)),
        )

    @staticmethod
    def calculate_finances(
        reservation: 'Reservation', currency: 'Currency', payed_amounts: Dict[int, Decimal]
    ) -> Dict[str, Any]:
        money_room = reservation.price_accepted
        money_extra = Decimal(0)
        money_total = money_room + money_extra
        money_payed = payed_amounts.get(reservation.quotation_id) or Decimal(0)
        balance = money_total - money_payed

        return {
            'money_room': currency.format(money_room),
            'money_extra': currency.format(money_extra),
            'total': currency.format(money_total),
            'payed': currency.format(money_payed),
            'balance': currency.format(balance),
            'has_balance': balance > Decimal(0),
        }

    @staticmethod
    def get_checkin(day: datetime.date) -> datetime.datetime:
        return datetime.datetime.combine(day, datetime.time(DEFAULT_CHECKIN_TIME))

    @staticmethod
    def get_checkout(day: datetime.date) -> datetime.datetime:
        return datetime.datetime.combine(day, datetime.time(DEFAULT_CHECKOUT_TIME))

    def init_cached_reservation(
        self, i: int, reservation: 'Reservation', grid: str, grid_id: int, day: datetime.date, room: 'ReservationRoom'
    ) -> Dict[str, Any]:
        if reservation.status == ReservationStatuses.CLOSE:
            status = reservation.status.name.lower()
        elif reservation.status == ReservationStatuses.HOLD:
            status = reservation.status.name.lower()
        elif len(reservation.rooms) > 1:
            status = 'group'
        else:
            status = None
        return {
            'pk': f"{reservation.id}-{room.id}-{i}",
            'reservation_id': reservation.id,
            'grid': grid,
            'grid_id': grid_id,
            'checkin': self.get_checkin(day),
            'checkout': self.get_checkout(day + datetime.timedelta(days=1)),
            'channel_id': reservation.get_id(),
            'source': reservation.source.value if reservation.source != ReservationSources.MANUAL else None,
            'source_code': reservation.source.name,
            'status': status,
            'adults': room.adults or room.guest_count,
            'children': room.children,
            'name': reservation.get_guest_name(),
            'phone': reservation.guest_phone,
            'close_reason': (
                reservation.close_reason.name if reservation.status == ReservationStatuses.CLOSE else None
            ),
            'close_reason_name': (
                reservation.close_reason.value if reservation.status == ReservationStatuses.CLOSE else None
            ),
            'comments': room.notes_info,
        }

    def make_cached_reservations(
        self,
        reservation: 'Reservation',
        house: 'House',
        rate_plans: Dict[int, 'RatePlan'],
        payed_amounts: Dict[int, Decimal],
    ) -> List[CachedReservation]:
        finances = self.calculate_finances(reservation, house.currency, payed_amounts)

        result = []
        i = 1
        item = None
        for room in reservation.rooms:
            rate_plan = rate_plans.get(room.rate_plan_id) if room.rate_plan_id is not None else None
            meal = rate_plan.meal.value if rate_plan is not None and rate_plan.meal is not None else ""

            for price in sorted(room.day_prices, key=lambda x: x.day):
                grid = 'room' if price.room_id is not None else 'roomtype'
                grid_id = price.room_id or price.roomtype_id
                if item is None:
                    item = self.init_cached_reservation(i, reservation, grid, grid_id, price.day, room)
                    item['meal'] = meal
                    item.update(finances)
                elif item['grid'] != grid or item['grid_id'] != grid_id:
                    item['split_right'] = True
                    result.append(CachedReservation(**item))
                    i += 1
                    item = self.init_cached_reservation(i, reservation, grid, grid_id, price.day, room)
                    item['meal'] = meal
                    item.update(finances)
                    item['split_left'] = True
                else:
                    item['checkout'] = self.get_checkout(price.day + datetime.timedelta(days=1))
            if item is not None:
                if not result:
                    result.append(CachedReservation(**item))
                elif result[-1].pk != item['pk']:
                    result.append(CachedReservation(**item))
        return result

    def process_reservations(self, ctx: Context) -> ResultE[Context]:
        if not ctx.reservations:
            return Success(ctx)
        for reservation in ctx.reservations:
            if reservation.status == ReservationStatuses.CANCEL:
                continue
            data = self.make_cached_reservations(reservation, ctx.house, ctx.rate_plans, ctx.payed_amounts)
            if data:
                ctx.cached_reservations += data
        return Success(ctx)

    def remove_canceled_reservations(self, ctx: Context) -> ResultE[Context]:
        if not ctx.reservations:
            return Success(ctx)
        for reservation in ctx.reservations:
            if reservation.status != ReservationStatuses.CANCEL:
                continue
            try:
                self._cache_repo.delete(ctx.house.id, reservation.id)
            except Exception as err:
                return self._error(
                    f"Error delete canceled Reservation ID={reservation.id} from Cache",
                    ctx,
                    self._case_errors.error,
                    exc=err,
                )
        return Success(ctx)

    def save_cache(self, ctx: Context) -> ResultE[Context]:
        if not ctx.cached_reservations:
            return Success(ctx)
        for_save = {}
        for item in ctx.cached_reservations:
            for_save.setdefault(item.reservation_id, []).append(item)
        for reservation_id, items in for_save.items():
            try:
                self._cache_repo.delete(ctx.house.id, reservation_id)
            except Exception as err:
                return self._error(
                    f"Error delete old Cache for Reservation ID={reservation_id}",
                    ctx,
                    self._case_errors.error,
                    exc=err,
                )
            for item in items:
                try:
                    self._cache_repo.save(ctx.house.id, item)
                except Exception as err:
                    return self._error(
                        f"Error save Cache Reservation ID={item.pk}", ctx, self._case_errors.error, exc=err
                    )
        return Success(ctx)

    def select_bot_user(self, ctx: Context) -> ResultE[Context]:
        if not ctx.reservations:
            # We don't need to select rate plans if not reservations
            return Success(ctx)
        try:
            data = self._members_repo.get_bot_user(ctx.house.company.id)
        except Exception as err:
            return self._error(
                f"Error select BOT User for Company ID={ctx.house.company.id}", ctx, self._case_errors.error, exc=err
            )
        if data == Nothing:
            return self._error(
                f"BOT User not found for Company ID={ctx.house.company.id}", ctx, self._case_errors.missed_user
            )
        ctx.user = data.unwrap()
        return Success(ctx)

    def select_payed_amounts(self, ctx: Context) -> ResultE[Context]:
        quotation_ids = [
            x.quotation_id for x in ctx.reservations if x.quotation_id is not None and x.quotation_id > 0
        ]
        if not quotation_ids:
            return Success(ctx)
        for quotation_id in quotation_ids:
            try:
                invoices = self.get_rpc_api(ctx).select_invoices_for_order(quotation_id)
                if not invoices:
                    continue
                ctx.payed_amounts[quotation_id] = sum(
                    [cf.get_decimal_or_none(x.amount_total - x.amount_residual) or Decimal(0) for x in invoices]
                )
            except Exception as err:
                return self._error(
                    f"Error select Invoices for Quotation ID={quotation_id} in House ID={ctx.house.id}",
                    ctx,
                    self._case_errors.error,
                    exc=err,
                )
        return Success(ctx)

    def select_rate_plans(self, ctx: Context) -> ResultE[Context]:
        if not ctx.reservations:
            return Success(ctx)
        ids = []
        for reservation in ctx.reservations:
            for room in reservation.rooms:
                if room.rate_plan_id is not None:
                    ids.append(room.rate_plan_id)
        ids = list(set(ids))
        if not ids:
            return Success(ctx)
        try:
            data = self._prices_repo.select_plans(ctx.house, ids=ids, user=ctx.user)
            ctx.rate_plans = {x.id: x for x in data}
            return Success(ctx)
        except Exception as err:
            return self._error(
                f"Error select Rate Plans for House ID={ctx.house.id}", ctx, self._case_errors.error, exc=err
            )

    def select_reservations(self, ctx: Context) -> ResultE[Context]:
        try:
            data = self._reservations_repo.select(
                house_id=ctx.house.id,
                start_date=ctx.start_date,
                end_date=ctx.end_date,
                pks=[ctx.pk] if ctx.pk is not None else None,
            )
            ctx.reservations = data
            return Success(ctx)
        except Exception as err:
            return self._error(
                f"Error select reservations for House ID={ctx.house.id}", ctx, self._case_errors.error, exc=err
            )
