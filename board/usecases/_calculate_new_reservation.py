import dataclasses
import datetime
from decimal import Decimal
from typing import Dict, List, Optional, TYPE_CHECKING, Union

import inject
from django.utils import timezone
from returns.maybe import Nothing
from returns.pipeline import flow
from returns.pointfree import bind_result
from returns.result import Success

from board.repositories import OccupancyRepo
from board.value_objects import ReservationCalcContext, ReservationErrors
from common import functions as cf
from common.mixins import HouseSelectMixin, RoomTypeSelectMixin
from common.value_objects import ResultE, ServiceBase, TPrices
from discounts.repositories import DiscountsRepo
from effective_tours.constants import DiscountTypes
from house_prices.entities import Rate
from house_prices.repositories import PricesRepo
from houses.repositories import HousesRepo, RoomTypesRepo

if TYPE_CHECKING:
    from discounts.entities import AvailabilityDiscount, Discount, LastMinDiscount, LOSDiscount
    from house_prices.entities import RatePlan
    from houses.entities import House, RoomType
    from members.entities import User


@dataclasses.dataclass
class Context:
    house_id: int
    roomtype_id: int
    plan_id: int
    start_date: datetime.date
    end_date: datetime.date
    guest_count: int
    user: 'User'
    rate_id: int = None
    house: 'House' = None
    room_type: 'RoomType' = None
    rate_plan: 'RatePlan' = None
    rate: Rate = None
    rates: List[Rate] = dataclasses.field(default_factory=list)
    prices: TPrices = dataclasses.field(default_factory=dict)
    discounts: Dict[
        DiscountTypes, List[Union['LastMinDiscount', 'AvailabilityDiscount', 'LOSDiscount', 'Discount']]
    ] = dataclasses.field(default_factory=dict)
    occupancies: Dict[datetime.date, Optional[int]] = dataclasses.field(default_factory=dict)
    price_restrictions: TPrices = dataclasses.field(default_factory=dict)


class CalculateNewReservation(ServiceBase, HouseSelectMixin, RoomTypeSelectMixin):
    @inject.autoparams()
    def __init__(
        self,
        houses_repo: HousesRepo,
        roomtypes_repo: RoomTypesRepo,
        prices_repo: PricesRepo,
        discounts_repo: DiscountsRepo,
        occupancy_repo: OccupancyRepo,
    ):
        self._houses_repo = houses_repo
        self._roomtypes_repo = roomtypes_repo
        self._prices_repo = prices_repo
        self._discounts_repo = discounts_repo
        self._occupancy_repo = occupancy_repo

        self._case_errors = ReservationErrors

    def execute(
        self,
        house_id: int,
        roomtype_id: int,
        plan_id: int,
        start_date: datetime.date,
        end_date: datetime.date,
        guest_count: int,
        user: 'User',
        rate_id: int = None,
    ) -> ResultE[ReservationCalcContext]:
        ctx = Context(
            house_id=house_id,
            roomtype_id=roomtype_id,
            plan_id=plan_id,
            start_date=start_date,
            end_date=end_date,
            guest_count=guest_count,
            user=user,
            rate_id=rate_id,
        )
        return flow(
            ctx,
            self.select_house,
            bind_result(self.select_room_type),
            bind_result(self.select_rate_plan),
            bind_result(self.select_rates),
            bind_result(self.select_rate_by_id),
            bind_result(self.select_rate_by_guest_count),
            bind_result(self.select_price_restrictions),
            bind_result(self.select_daily_prices),
            bind_result(self.select_discounts),
            bind_result(self.select_occupancies),
            bind_result(self.check_last_minute_discounts),
            bind_result(self.check_availability_discounts),
            bind_result(self.check_los_discounts),
            bind_result(self.check_min_prices),
            bind_result(self.make_result),
        )

    @staticmethod
    def apply_availability_discount(
        discounts: List['AvailabilityDiscount'], day: datetime.date, value: Decimal, inventory: Optional[int],
    ) -> Decimal:
        discounts = [x for x in discounts if x.free_rooms <= (inventory or 0) and x.start_date <= day <= x.end_date]
        if not discounts:
            return value
        discounts = sorted(discounts, key=lambda x: x.discount, reverse=True)
        return value * (1 - Decimal(discounts[0].discount) / 100)

    @staticmethod
    def apply_last_minute_discount(discounts: List['LastMinDiscount'], day: datetime.date, value: Decimal) -> Decimal:
        check_date = (day - timezone.localdate()).days
        discounts = [x for x in discounts if x.days_before >= check_date and x.start_date <= day <= x.end_date]
        if not discounts:
            return value
        discounts = sorted(discounts, key=lambda x: x.discount, reverse=True)
        return value * (1 - Decimal(discounts[0].discount) / 100)

    @staticmethod
    def apply_los_discount(
        discounts: List['LOSDiscount'], day: datetime.date, value: Decimal, nights: int
    ) -> Decimal:
        discounts = [x for x in discounts if x.nights <= nights and x.start_date <= day <= x.end_date]
        if not discounts:
            return value
        discounts = sorted(discounts, key=lambda x: x.discount, reverse=True)
        return value * (1 - Decimal(discounts[0].discount) / 100)

    @staticmethod
    def apply_min_price(restrictions: Dict[datetime.date, Decimal], day: datetime.date, value: Decimal) -> Decimal:
        if not restrictions or day not in restrictions:
            return value
        return max(value, restrictions.get(day, Decimal(0)))

    def check_availability_discounts(self, ctx: Context) -> ResultE[Context]:
        if not ctx.discounts or ctx.rate is None or not ctx.prices:
            return Success(ctx)
        discounts = ctx.discounts.get(DiscountTypes.AVAILABILITY, [])
        if not discounts:
            return Success(ctx)
        try:
            ctx.prices = {
                x: self.apply_availability_discount(discounts, x, y, ctx.occupancies.get(x))
                for x, y in ctx.prices.items()
            }
        except Exception as err:
            return self._error(
                f"Error apply Availability Discounts for Room Type ID={ctx.room_type.id} in House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        return Success(ctx)

    def check_last_minute_discounts(self, ctx: Context) -> ResultE[Context]:
        if not ctx.discounts or ctx.rate is None or not ctx.prices:
            return Success(ctx)
        discounts = ctx.discounts.get(DiscountTypes.LAST_MINUTE, [])
        if not discounts:
            return Success(ctx)
        try:
            ctx.prices = {x: self.apply_last_minute_discount(discounts, x, y) for x, y in ctx.prices.items()}
        except Exception as err:
            return self._error(
                f"Error apply Last Minute Discounts for Room Type ID={ctx.room_type.id} in House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        return Success(ctx)

    def check_los_discounts(self, ctx: Context) -> ResultE[Context]:
        if not ctx.discounts or ctx.rate is None or not ctx.prices:
            return Success(ctx)
        discounts = ctx.discounts.get(DiscountTypes.LOS, [])
        if not discounts:
            return Success(ctx)
        try:
            nights = (ctx.end_date - ctx.start_date).days
            ctx.prices = {x: self.apply_los_discount(discounts, x, y, nights) for x, y in ctx.prices.items()}
        except Exception as err:
            return self._error(
                f"Error apply Last Minute Discounts for Room Type ID={ctx.room_type.id} in House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        return Success(ctx)

    def check_min_prices(self, ctx: Context) -> ResultE[Context]:
        if ctx.rate is None or not ctx.price_restrictions:
            return Success(ctx)
        try:
            ctx.prices = {x: self.apply_min_price(ctx.price_restrictions, x, y) for x, y in ctx.prices.items()}
        except Exception as err:
            return self._error(
                f"Error apply Min Price Restriction for Room Type ID={ctx.room_type.id} in House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        return Success(ctx)

    @staticmethod
    def make_result(ctx: Context) -> ResultE[ReservationCalcContext]:
        return Success(
            ReservationCalcContext(
                house=ctx.house,
                room_type=ctx.room_type,
                rate_plan=ctx.rate_plan,
                rates=ctx.rates,
                rate=ctx.rate,
                prices=ctx.prices,
            )
        )

    def select_daily_prices(self, ctx: Context) -> ResultE[Context]:
        ctx.prices = {x: None for x in cf.get_days_for_period(ctx.start_date, ctx.end_date, exclude=True)}
        if ctx.rate is None:
            return Success(ctx)
        try:
            data = self._prices_repo.select_prices(
                ctx.rate,
                ctx.room_type,
                ctx.start_date,
                end_date=ctx.end_date - datetime.timedelta(days=1),
                user=ctx.user,
            )
        except Exception as err:
            return self._error(
                f"Error select prices for Rate ID={ctx.rate.id}", ctx, self._case_errors.error, exc=err
            )
        ctx.prices.update(data)
        return Success(ctx)

    def select_discounts(self, ctx: Context) -> ResultE[Context]:
        if not ctx.rate:
            # no rate -> no prices
            return Success(ctx)
        try:
            data = self._discounts_repo.select(ctx.house.id, ctx.room_type.id, only_active=True)
            for discount_type, discounts in data.items():
                ctx.discounts[discount_type] = [
                    x for x in discounts if ctx.rate_plan.id in x.rate_plans or not x.rate_plans
                ]
        except Exception as err:
            return self._error(
                f"Error select discounts for Room Type ID={ctx.room_type.id} in House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        return Success(ctx)

    def select_occupancies(self, ctx: Context) -> ResultE[Context]:
        if ctx.rate is None or not ctx.discounts.get(DiscountTypes.AVAILABILITY, []):
            return Success(ctx)
        try:
            ctx.occupancies = self._occupancy_repo.get(
                ctx.house.id, ctx.room_type.id, cf.get_days_for_period(ctx.start_date, ctx.end_date, exclude=True)
            )
        except Exception as err:
            return self._error(
                f"Error select occupancy for Room Type ID={ctx.room_type.id} in House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        return Success(ctx)

    def select_price_restrictions(self, ctx: Context) -> ResultE[Context]:
        if ctx.rate is None:
            return Success(ctx)
        try:
            ctx.price_restrictions = self._prices_repo.select_restrictions(
                ctx.house.id, ctx.room_type, ctx.rate_plan, ctx.start_date, ctx.end_date, ctx.rate
            )
        except Exception as err:
            return self._error(
                f"Error select price restrictions for Room Type ID={ctx.room_type.id} in House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        return Success(ctx)

    @staticmethod
    def select_rate_by_guest_count(ctx: Context) -> ResultE[Context]:
        if ctx.rate is not None or not ctx.rates:
            return Success(ctx)
        _rates = {x.occupancy: x for x in ctx.rates}

        # Got rate with required occupancy
        if ctx.guest_count in _rates:
            ctx.rate = _rates[ctx.guest_count]
            return Success(ctx)

        # Search rate with closest bigger occupancy
        for occupancy in sorted(_rates.keys()):
            if occupancy > ctx.guest_count:
                ctx.rate = _rates[occupancy]
                return Success(ctx)

        # Search rate wtih closest smaller occupancy
        for occupancy in sorted(_rates.keys(), reverse=True):
            if occupancy < ctx.guest_count:
                ctx.rate = _rates[occupancy]
                return Success(ctx)

        return Success(ctx)

    @staticmethod
    def select_rate_by_id(ctx: Context) -> ResultE[Context]:
        pk = cf.get_int_or_none(ctx.rate_id) or 0
        if pk <= 0 or not ctx.rates:
            return Success(ctx)
        _rates = {x.id: x for x in ctx.rates}
        ctx.rate = _rates.get(pk)
        return Success(ctx)

    def select_rate_plan(self, ctx: Context) -> ResultE[Context]:
        pk = cf.get_int_or_none(ctx.plan_id) or 0
        if pk <= 0:
            return self._error('Missed Rate Plan ID', ctx, self._case_errors.missed_rateplan)
        try:
            data = self._prices_repo.get_plan(ctx.house.odoo_id, pk, user=ctx.user)
        except Exception as err:
            return self._error(
                f"Error select Rate Plan ID={pk} in House ID={ctx.house.id}", ctx, self._case_errors.error, exc=err
            )
        if data == Nothing:
            return self._error(
                f"Unknown Rate Plan ID={pk} in House ID={ctx.house.id}", ctx, self._case_errors.missed_rateplan
            )
        ctx.rate_plan = data.unwrap()
        return Success(ctx)

    def select_rates(self, ctx: Context) -> ResultE[Context]:
        try:
            ctx.rates = self._prices_repo.select_rates(
                ctx.house, room_type=ctx.room_type, plan_id=ctx.rate_plan.id, user=ctx.user
            )
        except Exception as err:
            return self._error(
                f"Error select Rates for Room Type ID={ctx.room_type.id} in House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        return Success(ctx)
