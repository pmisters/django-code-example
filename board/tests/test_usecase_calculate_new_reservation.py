import datetime
from decimal import Decimal
from unittest.mock import Mock

import attr
import pytest
from returns.maybe import Nothing, Some
from returns.pipeline import is_successful

from board.usecases._calculate_new_reservation import CalculateNewReservation, Context  # noqa
from board.value_objects import ReservationCalcContext, ReservationErrors
from discounts.entities import AvailabilityDiscount, LOSDiscount, LastMinDiscount
from effective_tours.constants import DiscountTypes


@pytest.fixture()
def service() -> CalculateNewReservation:
    return CalculateNewReservation()


@pytest.fixture(scope="module")
def last_min_discount(house, room_type, rate_plan):
    return LastMinDiscount(
        id=1,
        house_id=house.id,
        roomtype_id=room_type.id,
        days_before=5,
        discount=15,
        start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=30),
        rate_plans=[rate_plan.id],
    )


@pytest.fixture(scope="module")
def availability_discount(house, room_type, rate_plan):
    return AvailabilityDiscount(
        id=1,
        house_id=house.id,
        roomtype_id=room_type.id,
        free_rooms=2,
        discount=15,
        start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=30),
        rate_plans=[rate_plan.id],
    )


@pytest.fixture(scope="module")
def los_discount(house, room_type, rate_plan):
    return LOSDiscount(
        id=1,
        house_id=house.id,
        roomtype_id=room_type.id,
        nights=3,
        discount=15,
        start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=30),
        rate_plans=[rate_plan.id],
    )


@pytest.fixture()
def context(house, room_type, rate_plan, user) -> Context:
    return Context(
        house_id=house.id,
        roomtype_id=room_type.id,
        plan_id=rate_plan.id,
        start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=2),
        guest_count=2,
        user=user,
    )


def test_missed_house_id(service: CalculateNewReservation, context: Context):
    context.house_id = None

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_error(service: CalculateNewReservation, context: Context):
    service._houses_repo = Mock(get=Mock(side_effect=RuntimeError("ERR")))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_house_fail(service: CalculateNewReservation, context: Context):
    service._houses_repo = Mock(get=Mock(return_value=Nothing))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_ok(service: CalculateNewReservation, context: Context, house):
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))

    result = service.select_house(context)
    assert is_successful(result)
    assert result.unwrap().house == house


def test_missed_roomtype_id(service: CalculateNewReservation, context: Context, house):
    context.house = house
    context.roomtype_id = None

    result = service.select_room_type(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_roomtype


def test_select_room_type_error(service: CalculateNewReservation, context: Context, house):
    service._roomtypes_repo = Mock(get=Mock(side_effect=RuntimeError("ERR")))
    context.house = house

    result = service.select_room_type(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_room_type_fail(service: CalculateNewReservation, context: Context, house):
    service._roomtypes_repo = Mock(get=Mock(return_value=Nothing))
    context.house = house

    result = service.select_room_type(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_roomtype


def test_select_room_type_ok(service: CalculateNewReservation, context: Context, house, room_type):
    service._roomtypes_repo = Mock(get=Mock(return_value=Some(room_type)))
    context.house = house

    result = service.select_room_type(context)
    assert is_successful(result), result.failure()
    assert result.unwrap().room_type == room_type


def test_missed_plan_id(service: CalculateNewReservation, context: Context, house):
    context.house = house
    context.plan_id = None

    result = service.select_rate_plan(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_rateplan


def test_select_rate_plan_error(service: CalculateNewReservation, context: Context, house):
    service._prices_repo = Mock(get_plan=Mock(side_effect=RuntimeError("ERR")))
    context.house = house

    result = service.select_rate_plan(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_rate_plan_fail(service: CalculateNewReservation, context: Context, house):
    service._prices_repo = Mock(get_plan=Mock(return_value=Nothing))
    context.house = house

    result = service.select_rate_plan(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_rateplan


def test_select_rate_plan_ok(service: CalculateNewReservation, context: Context, house, rate_plan):
    service._prices_repo = Mock(get_plan=Mock(return_value=Some(rate_plan)))
    context.house = house

    result = service.select_rate_plan(context)
    assert is_successful(result)
    assert result.unwrap().rate_plan == rate_plan


def test_select_rates_error(service: CalculateNewReservation, context: Context, house, room_type, rate_plan):
    service._prices_repo = Mock(select_rates=Mock(side_effect=RuntimeError("ERR")))
    context.house = house
    context.room_type = room_type
    context.rate_plan = rate_plan

    result = service.select_rates(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_rates_ok(service: CalculateNewReservation, context: Context, house, room_type, rate_plan, rate):
    service._prices_repo = Mock(select_rates=Mock(return_value=[rate]))
    context.house = house
    context.room_type = room_type
    context.rate_plan = rate_plan

    result = service.select_rates(context)
    assert is_successful(result)
    assert result.unwrap().rates == [rate]


def test_missed_rate_id(service: CalculateNewReservation, context: Context, house, room_type, rate_plan, rate):
    context.house = house
    context.room_type = room_type
    context.rate_plan = rate_plan
    context.rate_id = None
    context.rates = [rate]

    result = service.select_rate_by_id(context)
    assert is_successful(result)
    assert result.unwrap().rate is None


def test_select_rate_by_id_fail(
    service: CalculateNewReservation, context: Context, house, room_type, rate_plan, rate
):
    context.house = house
    context.room_type = room_type
    context.rate_plan = rate_plan
    context.rate_id = 9999
    context.rates = [rate]

    result = service.select_rate_by_id(context)
    assert is_successful(result)
    assert result.unwrap().rate is None


def test_select_rate_by_id_ok(service: CalculateNewReservation, context: Context, house, room_type, rate_plan, rate):
    context.house = house
    context.room_type = room_type
    context.rate_plan = rate_plan
    context.rate_id = rate.id
    context.rates = [rate]

    result = service.select_rate_by_id(context)
    assert is_successful(result)
    assert result.unwrap().rate == rate


def test_select_rate_by_guest_count_fail(
    service: CalculateNewReservation, context: Context, house, room_type, rate_plan, rate
):
    context.house = house
    context.room_type = room_type
    context.rate_plan = rate_plan
    context.rates = []

    result = service.select_rate_by_guest_count(context)
    assert is_successful(result)
    assert result.unwrap().rate is None


def test_select_rate_by_guest_count_only_bigger(
    service: CalculateNewReservation, context: Context, house, room_type, rate_plan, rate
):
    rate_with_3 = attr.evolve(rate, id=401, occupancy=3)
    rate_with_4 = attr.evolve(rate, id=402, occupancy=4)
    context.house = house
    context.room_type = room_type
    context.rate_plan = rate_plan
    context.rates = [rate_with_3, rate_with_4]

    result = service.select_rate_by_guest_count(context)
    assert is_successful(result)
    assert result.unwrap().rate == rate_with_3


def test_select_rate_by_guest_count_only_less(
    service: CalculateNewReservation, context: Context, house, room_type, rate_plan, rate
):
    rate_with_1 = attr.evolve(rate, id=401, occupancy=1)
    context.house = house
    context.room_type = room_type
    context.rate_plan = rate_plan
    context.rates = [rate_with_1]

    result = service.select_rate_by_guest_count(context)
    assert is_successful(result)
    assert result.unwrap().rate == rate_with_1


def test_select_rate_by_guest_count_ok(
    service: CalculateNewReservation, context: Context, house, room_type, rate_plan, rate
):
    rate_with_3 = attr.evolve(rate, id=401, occupancy=3)
    rate_with_4 = attr.evolve(rate, id=402, occupancy=4)
    context.house = house
    context.room_type = room_type
    context.rate_plan = rate_plan
    context.rates = [rate, rate_with_3, rate_with_4]

    result = service.select_rate_by_guest_count(context)
    assert is_successful(result)
    assert result.unwrap().rate == rate


def test_select_rate_by_guest_count_with_rate_id(
    service: CalculateNewReservation, context: Context, house, room_type, rate_plan, rate
):
    rate_with_2 = attr.evolve(rate, id=401, occupancy=2)
    context.house = house
    context.room_type = room_type
    context.rate_plan = rate_plan
    context.rate = rate
    context.rates = [rate_with_2]

    result = service.select_rate_by_guest_count(context)
    assert is_successful(result)
    assert result.unwrap().rate == rate


def test_select_daily_prices_with_no_rate(service: CalculateNewReservation, context: Context):
    context.rate = None

    result = service.select_daily_prices(context)
    assert is_successful(result)
    assert result.unwrap().prices == {
        datetime.date.today(): None,
        datetime.date.today() + datetime.timedelta(days=1): None,
    }


def test_select_daily_prices_error(service: CalculateNewReservation, context: Context, house, room_type, rate):
    service._prices_repo = Mock(select_prices=Mock(side_effect=RuntimeError("ERR")))
    context.house = house
    context.room_type = room_type
    context.rate = rate

    result = service.select_daily_prices(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_daily_prices_fail(service: CalculateNewReservation, context: Context, house, room_type, rate):
    service._prices_repo = Mock(select_prices=Mock(return_value={}))
    context.house = house
    context.room_type = room_type
    context.rate = rate

    result = service.select_daily_prices(context)
    assert is_successful(result)
    assert result.unwrap().prices == {
        datetime.date.today(): None,
        datetime.date.today() + datetime.timedelta(days=1): None,
    }


def test_select_daily_prices_ok(service: CalculateNewReservation, context: Context, house, room_type, rate):
    prices = {context.start_date: Decimal(100), context.start_date + datetime.timedelta(days=1): Decimal(110)}
    service._prices_repo = Mock(select_prices=Mock(return_value=prices))
    context.house = house
    context.room_type = room_type
    context.rate = rate

    result = service.select_daily_prices(context)
    assert is_successful(result)
    assert result.unwrap().prices == prices


def test_select_price_restrictions_error(
    service: CalculateNewReservation, context: Context, house, room_type, rate_plan, rate
):
    service._prices_repo = Mock(select_restrictions=Mock(side_effect=RuntimeError("ERR")))
    context.house = house
    context.room_type = room_type
    context.rate_plan = rate_plan
    context.rate = rate

    result = service.select_price_restrictions(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_price_restrictions_ok(
    service: CalculateNewReservation, context: Context, house, room_type, rate_plan, rate
):
    period = [datetime.date.today(), datetime.date.today() + datetime.timedelta(days=1)]

    service._prices_repo = Mock(
        select_restrictions=Mock(return_value={period[0]: Decimal(50), period[1]: Decimal(50)})
    )
    context.house = house
    context.room_type = room_type
    context.rate_plan = rate_plan
    context.rate = rate

    result = service.select_price_restrictions(context)
    assert is_successful(result)
    assert result.unwrap().price_restrictions == {period[0]: Decimal(50), period[1]: Decimal(50)}


def test_select_discounts_no_rate(service: CalculateNewReservation, context: Context, house, room_type, rate_plan):
    service._discounts_repo = Mock(select=Mock(side_effect=RuntimeError("ERR")))
    context.house = house
    context.room_type = room_type
    context.rate = None
    context.rate_plan = rate_plan
    context.prices = {context.start_date: None, context.start_date + datetime.timedelta(days=1): None}

    result = service.select_discounts(context)
    assert is_successful(result)
    assert result.unwrap().discounts == {}


def test_select_discounts_error(
    service: CalculateNewReservation, context: Context, house, room_type, rate, rate_plan
):
    service._discounts_repo = Mock(select=Mock(side_effect=RuntimeError("ERR")))
    context.house = house
    context.room_type = room_type
    context.rate = rate
    context.rate_plan = rate_plan
    context.prices = {context.start_date: Decimal(100), context.start_date + datetime.timedelta(days=1): Decimal(110)}

    result = service.select_discounts(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_discounts_ok(
    service: CalculateNewReservation, context: Context, house, room_type, rate, rate_plan, last_min_discount
):
    service._discounts_repo = Mock(select=Mock(return_value={DiscountTypes.LAST_MINUTE: [last_min_discount]}))
    context.house = house
    context.room_type = room_type
    context.rate = rate
    context.rate_plan = rate_plan
    context.prices = {context.start_date: Decimal(100), context.start_date + datetime.timedelta(days=1): Decimal(110)}

    result = service.select_discounts(context)
    assert is_successful(result)
    assert result.unwrap().discounts == {DiscountTypes.LAST_MINUTE: [last_min_discount]}


def test_select_discounts_ok_without_plans(
    service: CalculateNewReservation, context: Context, house, room_type, rate, rate_plan, last_min_discount
):
    _discount = attr.evolve(last_min_discount, rate_plans=[])
    service._discounts_repo = Mock(select=Mock(return_value={DiscountTypes.LAST_MINUTE: [_discount]}))
    context.house = house
    context.room_type = room_type
    context.rate = rate
    context.rate_plan = rate_plan
    context.prices = {context.start_date: Decimal(100), context.start_date + datetime.timedelta(days=1): Decimal(110)}

    result = service.select_discounts(context)
    assert is_successful(result)
    assert result.unwrap().discounts == {DiscountTypes.LAST_MINUTE: [_discount]}


def test_select_discounts_missed_rate_plan(
    service: CalculateNewReservation, context: Context, house, room_type, rate, rate_plan, last_min_discount
):
    service._discounts_repo = Mock(select=Mock(return_value={DiscountTypes.LAST_MINUTE: [last_min_discount]}))
    context.house = house
    context.room_type = room_type
    context.rate = rate
    context.rate_plan = attr.evolve(rate_plan, id=999)
    context.prices = {context.start_date: Decimal(100), context.start_date + datetime.timedelta(days=1): Decimal(110)}

    result = service.select_discounts(context)
    assert is_successful(result)
    assert result.unwrap().discounts == {DiscountTypes.LAST_MINUTE: []}


def test_select_occupancy_no_discounts(service: CalculateNewReservation, context: Context, house, room_type, rate):
    service._occupancy_repo = Mock(get=Mock(side_effect=RuntimeError("ERR")))
    context.house = house
    context.room_type = room_type
    context.rate = rate
    context.discounts = {DiscountTypes.AVAILABILITY: []}

    result = service.select_occupancies(context)
    assert is_successful(result)
    assert result.unwrap().occupancies == {}


def test_select_occupancy_error(
    service: CalculateNewReservation, context: Context, house, room_type, rate, availability_discount
):
    service._occupancy_repo = Mock(get=Mock(side_effect=RuntimeError("ERR")))
    context.house = house
    context.room_type = room_type
    context.rate = rate
    context.discounts = {DiscountTypes.AVAILABILITY: [availability_discount]}

    result = service.select_occupancies(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_occupancy_ok(
    service: CalculateNewReservation, context: Context, house, room_type, rate, availability_discount
):
    occupancies = {context.start_date: 1, context.start_date + datetime.timedelta(days=1): 2}
    service._occupancy_repo = Mock(get=Mock(return_value=occupancies))
    context.house = house
    context.room_type = room_type
    context.rate = rate
    context.discounts = {DiscountTypes.AVAILABILITY: [availability_discount]}

    result = service.select_occupancies(context)
    assert is_successful(result)
    assert result.unwrap().occupancies == occupancies


def test_check_last_minute_discounts_empty(
    service: CalculateNewReservation, context: Context, house, room_type, rate
):
    period = [context.start_date, context.start_date + datetime.timedelta(days=1)]
    context.house = house
    context.room_type = room_type
    context.rate = rate
    context.prices = {period[0]: Decimal(100), period[1]: Decimal(110)}
    context.discounts = {DiscountTypes.LAST_MINUTE: []}

    result = service.check_last_minute_discounts(context)
    assert is_successful(result)
    assert result.unwrap().prices == context.prices


def test_check_last_minute_discounts(
    service: CalculateNewReservation, context: Context, house, room_type, rate, last_min_discount
):
    period = [context.start_date + datetime.timedelta(days=5), context.start_date + datetime.timedelta(days=6)]
    context.house = house
    context.room_type = room_type
    context.rate = rate
    context.prices = {period[0]: Decimal(100), period[1]: Decimal(110)}
    context.discounts = {DiscountTypes.LAST_MINUTE: [last_min_discount]}

    result = service.check_last_minute_discounts(context)
    assert is_successful(result)

    assert result.unwrap().prices == {period[0]: Decimal(85), period[1]: Decimal(110)}


def test_check_availability_discounts_empty(
    service: CalculateNewReservation, context: Context, house, room_type, rate
):
    period = [context.start_date, context.start_date + datetime.timedelta(days=1)]
    context.house = house
    context.room_type = room_type
    context.rate = rate
    context.prices = {period[0]: Decimal(100), period[1]: Decimal(110)}
    context.discounts = {DiscountTypes.AVAILABILITY: []}

    result = service.check_availability_discounts(context)
    assert is_successful(result)
    assert result.unwrap().prices == context.prices


def test_check_availability_discounts(
    service: CalculateNewReservation, context: Context, house, room_type, rate, availability_discount
):
    period = [context.start_date, context.start_date + datetime.timedelta(days=1)]
    context.house = house
    context.room_type = room_type
    context.rate = rate
    context.prices = {period[0]: Decimal(100), period[1]: Decimal(110)}
    context.discounts = {DiscountTypes.AVAILABILITY: [availability_discount]}
    context.occupancies = {period[0]: 3, period[1]: 1}

    result = service.check_availability_discounts(context)
    assert is_successful(result)

    assert result.unwrap().prices == {period[0]: Decimal(85), period[1]: Decimal(110)}


def test_check_los_discounts_empty(service: CalculateNewReservation, context: Context, house, room_type, rate):
    period = [context.start_date, context.start_date + datetime.timedelta(days=1)]
    context.house = house
    context.room_type = room_type
    context.rate = rate
    context.prices = {period[0]: Decimal(100), period[1]: Decimal(110)}
    context.discounts = {DiscountTypes.LOS: []}

    result = service.check_los_discounts(context)
    assert is_successful(result)
    assert result.unwrap().prices == context.prices


def test_check_los_discounts(
    service: CalculateNewReservation, context: Context, house, room_type, rate, los_discount
):
    period = [
        context.start_date,
        context.start_date + datetime.timedelta(days=1),
        context.start_date + datetime.timedelta(days=2),
        context.start_date + datetime.timedelta(days=3),
    ]
    context.end_date = context.start_date + datetime.timedelta(days=4)
    context.house = house
    context.room_type = room_type
    context.rate = rate
    context.prices = {
        period[0]: Decimal(100),
        period[1]: Decimal(100),
        period[2]: Decimal(100),
        period[3]: Decimal(100),
    }
    context.discounts = {DiscountTypes.LOS: [los_discount]}

    result = service.check_los_discounts(context)
    assert is_successful(result)

    assert result.unwrap().prices == {
        period[0]: Decimal(85),
        period[1]: Decimal(85),
        period[2]: Decimal(85),
        period[3]: Decimal(85),
    }


def test_check_min_prices(service: CalculateNewReservation, context: Context, house, room_type, rate_plan, rate):
    period = [datetime.date.today(), datetime.date.today() + datetime.timedelta(days=1)]
    context.house = house
    context.room_type = room_type
    context.rate = rate
    context.prices = {period[0]: Decimal(80), period[1]: Decimal(110)}
    context.price_restrictions = {period[0]: Decimal(100), period[1]: Decimal(100)}

    result = service.check_min_prices(context)
    assert is_successful(result)
    assert result.unwrap().prices == {period[0]: Decimal(100), period[1]: Decimal(110)}


def test_success(
    service: CalculateNewReservation,
    context: Context,
    house,
    room_type,
    rate_plan,
    rate,
    user,
    last_min_discount,
    availability_discount,
    los_discount,
):
    rates = [rate, attr.evolve(rate, id=101, occupancy=3)]
    period = [context.start_date, context.start_date + datetime.timedelta(days=1)]

    service._houses_repo = Mock(get=Mock(return_value=Some(house)))
    service._roomtypes_repo = Mock(get=Mock(return_value=Some(room_type)))
    service._prices_repo = Mock(
        get_plan=Mock(return_value=Some(rate_plan)),
        select_rates=Mock(return_value=rates),
        select_prices=Mock(return_value={period[0]: Decimal(100), period[1]: Decimal(110)}),
        select_restrictions=Mock(return_value={period[0]: Decimal(80), period[1]: Decimal(80)}),
    )
    service._discounts_repo = Mock(
        select=Mock(
            return_value={
                DiscountTypes.LAST_MINUTE: [last_min_discount],
                DiscountTypes.AVAILABILITY: [availability_discount],
                DiscountTypes.LOS: [los_discount],
            }
        )
    )
    service._occupancy_repo = Mock(get=Mock(return_value={period[0]: 3, period[1]: 1}))

    result = service.execute(house.id, room_type.id, rate_plan.id, context.start_date, context.end_date, 2, user)
    assert is_successful(result), result.failure()

    ctx = result.unwrap()
    assert isinstance(ctx, ReservationCalcContext)
    assert ctx.room_type == room_type
    assert ctx.rate_plan == rate_plan
    assert ctx.rates == rates
    assert ctx.rate == rate
    assert ctx.prices == {period[0]: Decimal(80), period[1]: Decimal("93.50")}
