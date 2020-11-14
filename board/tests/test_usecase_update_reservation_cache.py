import datetime
from decimal import Decimal
from unittest.mock import Mock

import attr
import pytest
from django.utils import timezone
from returns.maybe import Nothing, Some
from returns.pipeline import is_successful

from board.entities import Reservation, ReservationDay, ReservationRoom
from board.usecases._update_reservation_cache import Context, UpdateReservationCache  # noqa
from board.value_objects import CachedReservation, ReservationErrors
from effective_tours.constants import Foods, ReservationSources, ReservationStatuses, RoomCloseReasons


@pytest.fixture()
def service():
    return UpdateReservationCache()


@pytest.fixture(scope='module')
def reservation(house, rate_plan, room_type):
    checkin = datetime.date.today()
    checkout = checkin + datetime.timedelta(days=1)
    return Reservation(
        id=111,
        house_id=house.id,
        connection_id=None,
        source=ReservationSources.MANUAL,
        channel=None,
        channel_id='',
        checkin=checkin,
        checkout=checkout,
        booked_at=timezone.now(),
        status=ReservationStatuses.NEW,
        is_verified=True,
        guest_name='John',
        guest_surname='Smith',
        guest_phone='+1-222-3344',
        price=Decimal(1120),
        price_accepted=Decimal(1121),
        netto_price=Decimal(1120),
        netto_price_accepted=Decimal(1121),
        quotation_id=321,
        rooms=[
            ReservationRoom(
                id=211,
                reservation_id=111,
                channel_id='',
                channel_rate_id='',
                checkin=checkin,
                checkout=checkout,
                rate_plan_id=rate_plan.id,
                adults=2,
                children=1,
                price=Decimal(1120),
                price_accepted=Decimal(1121),
                netto_price=Decimal(1120),
                netto_price_accepted=Decimal(1121),
                notes_info='XXX',
                day_prices=[
                    ReservationDay(
                        id=311,
                        reservation_room_id=211,
                        day=checkin,
                        roomtype_id=room_type.id,
                        price_original=Decimal(1120),
                        price_accepted=Decimal(1121),
                        currency=house.currency.code,
                    )
                ],
            )
        ],
    )


@pytest.fixture()
def context(house):
    return Context(house_id=house.id)


def test_missed_house_id(service: UpdateReservationCache, context: Context):
    context.house_id = None

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_error(service: UpdateReservationCache, context: Context):
    service._houses_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_house_fail(service: UpdateReservationCache, context: Context):
    service._houses_repo = Mock(get=Mock(return_value=Nothing))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_ok(service: UpdateReservationCache, context: Context, house):
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))

    result = service.select_house(context)
    assert is_successful(result)
    assert result.unwrap().house == house


def test_select_reservations_error(service: UpdateReservationCache, context: Context, house):
    service._reservations_repo = Mock(select=Mock(side_effect=RuntimeError('ERR')))
    context.house = house

    result = service.select_reservations(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_reservations_fail(service: UpdateReservationCache, context: Context, house):
    service._reservations_repo = Mock(select=Mock(return_value=[]))
    context.house = house

    result = service.select_reservations(context)
    assert is_successful(result)
    assert result.unwrap().reservations == []


def test_select_reservations_ok(service: UpdateReservationCache, context: Context, house, reservation):
    service._reservations_repo = Mock(select=Mock(return_value=[reservation]))
    context.house = house

    result = service.select_reservations(context)
    assert is_successful(result)
    assert result.unwrap().reservations == [reservation]


def test_select_bot_user_error(service: UpdateReservationCache, context: Context, house, reservation):
    service._members_repo = Mock(get_bot_user=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.reservations = [reservation]

    result = service.select_bot_user(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_bot_user_fail(service: UpdateReservationCache, context: Context, house, reservation):
    service._members_repo = Mock(get_bot_user=Mock(return_value=Nothing))
    context.house = house
    context.reservations = [reservation]

    result = service.select_bot_user(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_user


def test_select_bot_user_ok(service: UpdateReservationCache, context: Context, house, reservation, user):
    service._members_repo = Mock(get_bot_user=Mock(return_value=Some(user)))
    context.house = house
    context.reservations = [reservation]

    result = service.select_bot_user(context)
    assert is_successful(result), result.failure()
    assert result.unwrap().user == user


def test_select_rate_plans_error(service: UpdateReservationCache, context: Context, house, reservation, user):
    service._prices_repo = Mock(select_plans=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.reservations = [reservation]
    context.user = user

    result = service.select_rate_plans(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_rate_plans_ok(service: UpdateReservationCache, context: Context, house, reservation, rate_plan, user):
    service._prices_repo = Mock(select_plans=Mock(return_value=[rate_plan]))
    context.house = house
    context.reservations = [reservation]
    context.user = user

    result = service.select_rate_plans(context)
    assert is_successful(result), result.failure()
    assert result.unwrap().rate_plans == {rate_plan.id: rate_plan}


def test_select_payed_amounts_error(service: UpdateReservationCache, context: Context, house, reservation, user):
    context.house = house
    context.reservations = [reservation]
    context.user = user
    context.api = Mock(select_invoices_for_order=Mock(side_effect=RuntimeError('ERR')))

    result = service.select_payed_amounts(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_payed_amounts_empty(service: UpdateReservationCache, context: Context, house, user):
    context.house = house
    context.reservations = []
    context.user = user
    context.api = Mock(select_invoices_for_order=Mock(side_effect=RuntimeError('ERR')))

    result = service.select_payed_amounts(context)
    assert is_successful(result)
    assert result.unwrap().payed_amounts == {}


def test_select_payed_amounts_ok(service: UpdateReservationCache, context: Context, house, reservation, user):
    context.house = house
    context.reservations = [
        attr.evolve(reservation, quotation_id=321),
        attr.evolve(reservation, id=123, quotation_id=322),
        attr.evolve(reservation, id=124, quotation_id=None),
    ]
    context.user = user
    context.api = Mock(
        select_invoices_for_order=Mock(return_value=[Mock(id=987, amount_total=50.0, amount_residual=20.0)])
    )

    result = service.select_payed_amounts(context)
    assert is_successful(result)
    assert result.unwrap().payed_amounts == {321: Decimal(30), 322: Decimal(30)}

    context.api.select_invoices_for_order.assert_any_call(321)
    context.api.select_invoices_for_order.assert_any_call(322)


def test_make_cached_reservations_full(service: UpdateReservationCache, house, reservation, room_type, rate_plan):
    checkin = datetime.date.today()
    checkout = checkin + datetime.timedelta(days=1)

    result = service.make_cached_reservations(reservation, house, {rate_plan.id: rate_plan}, {321: Decimal(30)})

    assert len(result) == 1
    assert isinstance(result[0], CachedReservation)
    assert result[0].pk == '111-211-1'
    assert result[0].reservation_id == 111
    assert result[0].grid == 'roomtype'
    assert result[0].grid_id == room_type.id
    assert result[0].checkin == datetime.datetime.combine(checkin, datetime.time(14))
    assert result[0].checkout == datetime.datetime.combine(checkout, datetime.time(11))
    assert result[0].source is None
    assert result[0].source_code == ReservationSources.MANUAL.name
    assert result[0].status is None
    assert result[0].adults == 2
    assert result[0].children == 1
    assert result[0].meal == Foods.RO.value
    assert result[0].name == 'John Smith'
    assert result[0].phone == '+1-222-3344'
    assert result[0].money_room == '$1121.00'
    assert result[0].money_extra == '$0.00'
    assert result[0].total == '$1121.00'
    assert result[0].payed == '$30.00'
    assert result[0].balance == '$1091.00'
    assert result[0].has_balance


def test_make_cached_reservations_split(service: UpdateReservationCache, house, rate_plan, room_type):
    checkin = datetime.date.today()
    checkout = checkin + datetime.timedelta(days=2)
    room_type_2 = attr.evolve(room_type, id=101)
    reservation = Reservation(
        id=111,
        house_id=house.id,
        connection_id=None,
        source=ReservationSources.MANUAL,
        channel=None,
        channel_id='',
        checkin=checkin,
        checkout=checkout,
        booked_at=timezone.now(),
        status=ReservationStatuses.NEW,
        is_verified=True,
        guest_name='John',
        guest_surname='Smith',
        guest_phone='+1-222-3344',
        price=Decimal(1120),
        price_accepted=Decimal(1121),
        netto_price=Decimal(1120),
        netto_price_accepted=Decimal(1121),
        quotation_id=321,
        rooms=[
            ReservationRoom(
                id=211,
                reservation_id=111,
                channel_id='',
                channel_rate_id='',
                checkin=checkin,
                checkout=checkout,
                rate_plan_id=rate_plan.id,
                adults=2,
                children=1,
                price=Decimal(1120),
                price_accepted=Decimal(1121),
                netto_price=Decimal(1120),
                netto_price_accepted=Decimal(1121),
                day_prices=[
                    ReservationDay(
                        id=311,
                        reservation_room_id=211,
                        day=checkin,
                        roomtype_id=room_type.id,
                        price_original=Decimal(560),
                        price_accepted=Decimal(561),
                        currency=house.currency.code,
                    ),
                    ReservationDay(
                        id=311,
                        reservation_room_id=211,
                        day=checkin + datetime.timedelta(days=1),
                        roomtype_id=room_type_2.id,
                        price_original=Decimal(560),
                        price_accepted=Decimal(561),
                        currency=house.currency.code,
                    ),
                ],
            )
        ],
    )

    result = service.make_cached_reservations(reservation, house, {rate_plan.id: rate_plan}, {321: Decimal(30)})

    assert len(result) == 2
    assert all([isinstance(x, CachedReservation) for x in result])

    assert result[0].pk == '111-211-1'
    assert result[0].reservation_id == 111
    assert result[0].grid == 'roomtype'
    assert result[0].grid_id == room_type.id
    assert result[0].checkin == datetime.datetime.combine(checkin, datetime.time(14))
    assert result[0].checkout == datetime.datetime.combine(checkin + datetime.timedelta(days=1), datetime.time(11))
    assert result[0].source is None
    assert result[0].source_code == ReservationSources.MANUAL.name
    assert result[0].status is None
    assert result[0].adults == 2
    assert result[0].children == 1
    assert result[0].meal == Foods.RO.value
    assert result[0].name == 'John Smith'
    assert result[0].phone == '+1-222-3344'
    assert result[0].money_room == '$1121.00'
    assert result[0].money_extra == '$0.00'
    assert result[0].total == '$1121.00'
    assert result[0].payed == '$30.00'
    assert result[0].balance == '$1091.00'
    assert result[0].has_balance

    assert result[1].pk == '111-211-2'
    assert result[1].reservation_id == 111
    assert result[1].grid == 'roomtype'
    assert result[1].grid_id == room_type_2.id
    assert result[1].checkin == datetime.datetime.combine(checkin + datetime.timedelta(days=1), datetime.time(14))
    assert result[1].checkout == datetime.datetime.combine(checkout, datetime.time(11))
    assert result[1].source is None
    assert result[1].source_code == ReservationSources.MANUAL.name
    assert result[0].status is None
    assert result[1].adults == 2
    assert result[1].children == 1
    assert result[1].meal == Foods.RO.value
    assert result[1].name == 'John Smith'
    assert result[1].phone == '+1-222-3344'
    assert result[1].money_room == '$1121.00'
    assert result[1].money_extra == '$0.00'
    assert result[1].total == '$1121.00'
    assert result[1].payed == '$30.00'
    assert result[1].balance == '$1091.00'
    assert result[1].has_balance


def test_make_cached_close_room_reservation(
    service: UpdateReservationCache, house, reservation, room_type, rate_plan
):
    checkin = datetime.date.today()
    checkout = checkin + datetime.timedelta(days=1)
    _reservation = attr.evolve(
        reservation, status=ReservationStatuses.CLOSE, close_reason=RoomCloseReasons.MAINTENANCE
    )

    result = service.make_cached_reservations(_reservation, house, {rate_plan.id: rate_plan}, {})

    assert len(result) == 1
    assert isinstance(result[0], CachedReservation)
    assert result[0].pk == '111-211-1'
    assert result[0].reservation_id == 111
    assert result[0].grid == 'roomtype'
    assert result[0].grid_id == room_type.id
    assert result[0].checkin == datetime.datetime.combine(checkin, datetime.time(14))
    assert result[0].checkout == datetime.datetime.combine(checkout, datetime.time(11))
    assert result[0].source is None
    assert result[0].source_code == ReservationSources.MANUAL.name
    assert result[0].status == 'close'
    assert result[0].adults == 2
    assert result[0].children == 1
    assert result[0].meal == Foods.RO.value
    assert result[0].name == 'John Smith'
    assert result[0].phone == '+1-222-3344'
    assert result[0].money_room == '$1121.00'
    assert result[0].money_extra == '$0.00'
    assert result[0].total == '$1121.00'
    assert result[0].payed == '$0.00'
    assert result[0].balance == '$1121.00'
    assert result[0].has_balance
    assert result[0].close_reason == RoomCloseReasons.MAINTENANCE.name
    assert result[0].close_reason_name == RoomCloseReasons.MAINTENANCE.value
    assert result[0].comments == 'XXX'


def test_get_checkin(service: UpdateReservationCache):
    assert service.get_checkin(datetime.date(2020, 12, 15)) == datetime.datetime(2020, 12, 15, 14)


def test_get_checkout(service: UpdateReservationCache):
    assert service.get_checkout(datetime.date(2020, 12, 15)) == datetime.datetime(2020, 12, 15, 11)


def test_calculate_finances(service: UpdateReservationCache, house, reservation):
    _reservation = attr.evolve(reservation, price=Decimal(1120), netto_price=Decimal(1120))

    result = service.calculate_finances(_reservation, house.currency, {321: Decimal(30)})
    assert result == {
        'money_room': '$1121.00',
        'money_extra': '$0.00',
        'total': '$1121.00',
        'payed': '$30.00',
        'balance': '$1091.00',
        'has_balance': True,
    }


def test_process_reservations(service: UpdateReservationCache, context: Context, house, reservation):
    context.house = house
    context.reservations = [reservation]

    result = service.process_reservations(context)
    assert is_successful(result)

    assert len(result.unwrap().cached_reservations) == 1
    assert all([isinstance(x, CachedReservation) for x in result.unwrap().cached_reservations])


def test_save_cache_error(service: UpdateReservationCache, context: Context, house, room_type):
    service._cache_repo = Mock(save=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.cached_reservations = [
        CachedReservation(
            pk='111-1',
            reservation_id=111,
            grid='roomtype',
            grid_id=room_type.id,
            checkin=datetime.datetime.combine(datetime.date.today(), datetime.time(14)),
            checkout=datetime.datetime.combine(datetime.date.today() + datetime.timedelta(days=1), datetime.time(11)),
        )
    ]

    result = service.save_cache(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_save_cache_ok(service: UpdateReservationCache, context: Context, house, room_type):
    service._cache_repo = Mock(save=Mock(return_value=True))
    context.house = house
    context.cached_reservations = [
        CachedReservation(
            pk='111-1',
            reservation_id=111,
            grid='roomtype',
            grid_id=room_type.id,
            checkin=datetime.datetime.combine(datetime.date.today(), datetime.time(14)),
            checkout=datetime.datetime.combine(datetime.date.today() + datetime.timedelta(days=1), datetime.time(11)),
        )
    ]

    result = service.save_cache(context)
    assert is_successful(result)


def test_success(service: UpdateReservationCache, house, reservation, rate_plan, user):
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))
    service._reservations_repo = Mock(select=Mock(return_value=[reservation]))
    service._cache_repo = Mock(save=Mock(return_value=True), delete=Mock(return_value=None))
    service._prices_repo = Mock(select_plans=Mock(return_value=[rate_plan]))
    service._members_repo = Mock(get_bot_user=Mock(return_value=Some(user)))
    service.get_rpc_api = Mock(
        return_value=Mock(
            select_invoices_for_order=Mock(return_value=[Mock(id=987, amount_total=50.0, amount_residual=20.0)])
        )
    )

    result = service.execute(house_id=house.id)
    assert is_successful(result)
