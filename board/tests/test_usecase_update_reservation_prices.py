import datetime
from decimal import Decimal
from unittest.mock import Mock

import attr
import pytest
from django.utils import timezone
from returns.maybe import Nothing, Some
from returns.pipeline import is_successful

from board.entities import Reservation, ReservationDay, ReservationRoom
from board.usecases._update_reservation_prices import Context, UpdateReservationPrices  # noqa
from board.value_objects import ReservationErrors
from common import functions as cf
from effective_tours.constants import ReservationSources, ReservationStatuses


@pytest.fixture()
def service() -> UpdateReservationPrices:
    return UpdateReservationPrices()


@pytest.fixture(scope='module')
def reservation(house, room_type):
    checkin = datetime.date.today()
    checkout = checkin + datetime.timedelta(days=3)
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
        status=ReservationStatuses.MODIFY,
        price=Decimal(1120),
        netto_price=Decimal(1120),
        rooms=[
            ReservationRoom(
                id=211,
                reservation_id=111,
                channel_id='',
                channel_rate_id='',
                checkin=checkin,
                checkout=checkout,
                rate_plan_id=499,
                rate_plan_id_original=499,
                adults=2,
                children=1,
                price=Decimal(1120),
                price_accepted=Decimal(1120),
                netto_price=Decimal(1120),
                netto_price_accepted=Decimal(1120),
                day_prices=[
                    ReservationDay(
                        id=311,
                        reservation_room_id=211,
                        day=checkin,
                        roomtype_id=room_type.id,
                        price_original=Decimal(1120),
                        price_accepted=Decimal(1120),
                        currency=house.currency.code,
                    ),
                    ReservationDay(
                        id=312,
                        reservation_room_id=211,
                        day=checkin + datetime.timedelta(days=1),
                        roomtype_id=room_type.id,
                        price_original=Decimal(1120),
                        price_accepted=Decimal(1120),
                        currency=house.currency.code,
                    ),
                    ReservationDay(
                        id=313,
                        reservation_room_id=211,
                        day=checkin + datetime.timedelta(days=2),
                        roomtype_id=room_type.id,
                        price_original=Decimal(1120),
                        price_accepted=Decimal(1120),
                        currency=house.currency.code,
                    ),
                ],
            )
        ],
    )


@pytest.fixture()
def context(house, reservation, rate_plan, room, user) -> Context:
    prices = {}
    for day in cf.get_days_for_period(datetime.date.today(), datetime.date.today() + datetime.timedelta(days=4)):
        prices[day] = {'room': room.id, 'price': Decimal(1200), 'day': day}
    return Context(
        house_id=house.id,
        pk=reservation.id,
        room_id=reservation.rooms[0].id,
        user=user,
        plan_id=rate_plan.id,
        prices=prices,
    )


def test_missed_house_id(service: UpdateReservationPrices, context: Context):
    context.house_id = None

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_error(service: UpdateReservationPrices, context: Context):
    service._houses_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_house_fail(service: UpdateReservationPrices, context: Context):
    service._houses_repo = Mock(get=Mock(return_value=Nothing))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_ok(service: UpdateReservationPrices, context: Context, house):
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))

    result = service.select_house(context)
    assert is_successful(result)
    assert result.unwrap().house == house


def test_select_reservation_missed_pk(service: UpdateReservationPrices, context: Context, house):
    context.house = house
    context.pk = None

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_error(service: UpdateReservationPrices, context: Context, house):
    service._reservations_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_reservation_fail(service: UpdateReservationPrices, context: Context, house):
    service._reservations_repo = Mock(get=Mock(return_value=Nothing))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_ok(service: UpdateReservationPrices, context: Context, house, reservation):
    service._reservations_repo = Mock(get=Mock(return_value=Some(reservation)))
    context.house = house

    result = service.select_reservation(context)
    assert is_successful(result)
    assert result.unwrap().source == reservation


def test_check_reservation_wrong_house(service: UpdateReservationPrices, context: Context, house, reservation):
    context.house = house
    context.source = attr.evolve(reservation, house_id=999)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_check_reservation_room_close(service: UpdateReservationPrices, context: Context, house, reservation):
    context.house = house
    context.source = attr.evolve(reservation, status=ReservationStatuses.CLOSE)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_check_reservation_canceled(service: UpdateReservationPrices, context: Context, house, reservation):
    context.house = house
    context.source = attr.evolve(reservation, status=ReservationStatuses.CANCEL)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_room_missed_id(service: UpdateReservationPrices, context: Context, house, reservation):
    context.house = house
    context.source = reservation
    context.room_id = None

    result = service.select_reservation_room(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_room_wrong_id(service: UpdateReservationPrices, context: Context, house, reservation):
    context.house = house
    context.source = reservation
    context.room_id = 999

    result = service.select_reservation_room(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_room_ok(service: UpdateReservationPrices, context: Context, house, reservation):
    context.house = house
    context.source = reservation

    result = service.select_reservation_room(context)
    assert is_successful(result)
    assert result.unwrap().reservation_room == reservation.rooms[0]


def test_is_allow_update_period_fail(service: UpdateReservationPrices, context: Context, house, reservation):
    context.house = house
    context.source = attr.evolve(reservation, source=ReservationSources.BOOKING)
    context.reservation_room = reservation.rooms[0]

    result = service.is_allow_update_period(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.wrong_period


def test_is_allow_update_period_ok_for_ota(service: UpdateReservationPrices, context: Context, house, reservation):
    context.house = house
    context.source = attr.evolve(reservation, source=ReservationSources.BOOKING)
    context.reservation_room = reservation.rooms[0]
    context.prices = {
        k: v for k, v in context.prices.items() if reservation.rooms[0].checkin <= k < reservation.rooms[0].checkout
    }

    result = service.is_allow_update_period(context)
    assert is_successful(result)


def test_is_allow_update_period_ok_for_manual(service: UpdateReservationPrices, context: Context, house, reservation):
    context.house = house
    context.source = reservation
    context.reservation_room = reservation.rooms[0]

    result = service.is_allow_update_period(context)
    assert is_successful(result)


def test_select_rate_plan_error(service: UpdateReservationPrices, context: Context, house):
    service._prices_repo = Mock(get_plan=Mock(side_effect=RuntimeError('ERR')))
    context.house = house

    result = service.select_rate_plan(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_rate_plan_fail(service: UpdateReservationPrices, context: Context, house):
    service._prices_repo = Mock(get_plan=Mock(return_value=Nothing))
    context.house = house

    result = service.select_rate_plan(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_rateplan


def test_select_rate_plan_ok(service: UpdateReservationPrices, context: Context, house, rate_plan):
    service._prices_repo = Mock(get_plan=Mock(return_value=Some(rate_plan)))
    context.house = house

    result = service.select_rate_plan(context)
    assert is_successful(result)
    assert result.unwrap().rate_plan == rate_plan


def test_select_cancellation_policy_for_plan_without_it(
    service: UpdateReservationPrices, context: Context, house, rate_plan, reservation
):
    service._policies_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.source = reservation
    context.reservation_room = reservation.rooms[0]
    context.rate_plan = attr.evolve(rate_plan, policy_id=0)

    result = service.select_cancellation_policy(context)
    assert is_successful(result)
    assert result.unwrap().rate_plan.policy is None


def test_select_cancellation_policy_if_plan_not_changes(
    service: UpdateReservationPrices, context: Context, house, rate_plan, reservation
):
    service._policies_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.source = reservation
    context.reservation_room = reservation.rooms[0]
    context.rate_plan = attr.evolve(rate_plan, id=reservation.rooms[0].rate_plan_id)

    result = service.select_cancellation_policy(context)
    assert is_successful(result)
    assert result.unwrap().rate_plan.policy is None


def test_select_cancellation_policy_error(
    service: UpdateReservationPrices, context: Context, house, rate_plan, reservation
):
    service._policies_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.source = reservation
    context.reservation_room = reservation.rooms[0]
    context.rate_plan = rate_plan

    result = service.select_cancellation_policy(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_cancellation_policy_fail(
    service: UpdateReservationPrices, context: Context, house, rate_plan, reservation
):
    service._policies_repo = Mock(get=Mock(return_value=Nothing))
    context.house = house
    context.source = reservation
    context.reservation_room = reservation.rooms[0]
    context.rate_plan = rate_plan

    result = service.select_cancellation_policy(context)
    assert is_successful(result)
    assert result.unwrap().rate_plan.policy is None


def test_select_cancellation_policy_ok(
    service: UpdateReservationPrices, context: Context, house, rate_plan, cancellation_policy, reservation
):
    service._policies_repo = Mock(get=Mock(return_value=Some(cancellation_policy)))
    context.house = house
    context.source = reservation
    context.reservation_room = reservation.rooms[0]
    context.rate_plan = rate_plan

    result = service.select_cancellation_policy(context)
    assert is_successful(result)
    assert result.unwrap().rate_plan.policy == cancellation_policy


def test_select_rooms_error(service: UpdateReservationPrices, context: Context, house):
    service._rooms_repo = Mock(select=Mock(side_effect=RuntimeError('ERR')))
    context.house = house

    result = service.select_rooms(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_rooms_ok(service: UpdateReservationPrices, context: Context, house, room):
    service._rooms_repo = Mock(select=Mock(return_value=[room]))
    context.house = house

    result = service.select_rooms(context)
    assert is_successful(result)
    assert result.unwrap().rooms == {room.id: room}


def test_select_room_types_error(service: UpdateReservationPrices, context: Context, house):
    service._roomtypes_repo = Mock(select=Mock(side_effect=RuntimeError('ERR')))
    context.house = house

    result = service.select_room_types(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_room_types_ok(service: UpdateReservationPrices, context: Context, house, room_type):
    service._roomtypes_repo = Mock(select=Mock(return_value=[room_type]))
    context.house = house

    result = service.select_room_types(context)
    assert is_successful(result)
    assert result.unwrap().room_types == {room_type.id: room_type}


def test_make_reservation_from_data_with_same_plan(
    service: UpdateReservationPrices, context: Context, house, room_type, room, rate_plan, reservation
):
    context.house = house
    context.source = reservation
    context.reservation_room = reservation.rooms[0]
    context.room_types = {room_type.id: room_type}
    context.rooms = {room.id: room}
    context.rate_plan = attr.evolve(rate_plan, id=reservation.rooms[0].rate_plan_id)

    result = service.make_reservation_from_data(context)
    assert is_successful(result)

    _reservation = result.unwrap().reservation

    assert len(_reservation.rooms[0].day_prices) == len(context.prices)
    assert [x.day for x in _reservation.rooms[0].day_prices] == list(context.prices.keys())
    for price in _reservation.rooms[0].day_prices:
        assert price.price_accepted == Decimal(1200)
        assert price.room_id == room.id
        assert price.roomtype_id == room_type.id
        assert price.tax == Decimal(120)

    assert _reservation.rooms[0].netto_price == Decimal(1120)
    assert _reservation.rooms[0].netto_price_accepted == Decimal(6000)
    assert _reservation.rooms[0].price == Decimal(1120)
    assert _reservation.rooms[0].price_accepted == Decimal(6600)
    assert _reservation.rooms[0].tax == Decimal(600)
    assert _reservation.rooms[0].rate_plan_id == 499
    assert _reservation.rooms[0].policy == {}
    assert _reservation.rooms[0].checkin == datetime.date.today()
    assert _reservation.rooms[0].checkout == datetime.date.today() + datetime.timedelta(days=5)

    assert _reservation.netto_price == Decimal(1120)
    assert _reservation.netto_price_accepted == Decimal(6000)
    assert _reservation.price == Decimal(1120)
    assert _reservation.price_accepted == Decimal(6600)
    assert _reservation.tax == Decimal(600)
    assert _reservation.checkin == datetime.date.today()
    assert _reservation.checkout == datetime.date.today() + datetime.timedelta(days=5)


def test_make_reservation_from_data_with_new_plan(
    service: UpdateReservationPrices,
    context: Context,
    house,
    room_type,
    room,
    rate_plan,
    reservation,
    cancellation_policy,
):
    context.house = house
    context.source = reservation
    context.reservation_room = reservation.rooms[0]
    context.room_types = {room_type.id: room_type}
    context.rooms = {room.id: room}
    context.rate_plan = attr.evolve(rate_plan, policy=cancellation_policy)

    result = service.make_reservation_from_data(context)
    assert is_successful(result)

    _reservation = result.unwrap().reservation
    assert len(_reservation.rooms[0].day_prices) == len(context.prices)
    assert [x.day for x in _reservation.rooms[0].day_prices] == list(context.prices.keys())
    for price in _reservation.rooms[0].day_prices:
        assert price.price_accepted == Decimal(1200)
        assert price.room_id == room.id
        assert price.roomtype_id == room_type.id
        assert price.tax == Decimal(120)

    assert _reservation.rooms[0].netto_price == Decimal(1120)
    assert _reservation.rooms[0].netto_price_accepted == Decimal(6000)
    assert _reservation.rooms[0].price == Decimal(1120)
    assert _reservation.rooms[0].price_accepted == Decimal(6600)
    assert _reservation.rooms[0].tax == Decimal(600)
    assert _reservation.rooms[0].rate_plan_id == rate_plan.id
    assert _reservation.rooms[0].policy == {
        'name': 'Charge for 2 nights in case of cancelation',
        'policy_items': [{'days': None, 'charge': 2, 'charge_type': 'NIGHT'}]
    }
    assert _reservation.rooms[0].checkin == datetime.date.today()
    assert _reservation.rooms[0].checkout == datetime.date.today() + datetime.timedelta(days=5)

    assert _reservation.netto_price == Decimal(1120)
    assert _reservation.netto_price_accepted == Decimal(6000)
    assert _reservation.price == Decimal(1120)
    assert _reservation.price_accepted == Decimal(6600)
    assert _reservation.tax == Decimal(600)
    assert _reservation.checkin == datetime.date.today()
    assert _reservation.checkout == datetime.date.today() + datetime.timedelta(days=5)


def test_make_reservation_from_data_for_more_rooms(
    service: UpdateReservationPrices,
    context: Context,
    house,
    room_type,
    room,
    rate_plan,
    reservation,
    cancellation_policy,
):
    reservation.rooms.append(attr.evolve(reservation.rooms[0], id=212))

    context.house = house
    context.source = reservation
    context.reservation_room = reservation.rooms[0]
    context.room_types = {room_type.id: room_type}
    context.rooms = {room.id: room}
    context.rate_plan = attr.evolve(rate_plan, policy=cancellation_policy)

    result = service.make_reservation_from_data(context)
    assert is_successful(result)

    _reservation = result.unwrap().reservation
    assert len(_reservation.rooms[0].day_prices) == len(context.prices)
    assert [x.day for x in _reservation.rooms[0].day_prices] == list(context.prices.keys())
    for price in _reservation.rooms[0].day_prices:
        assert price.price_accepted == Decimal(1200)
        assert price.room_id == room.id
        assert price.roomtype_id == room_type.id
        assert price.tax == Decimal(120)

    assert _reservation.rooms[0].netto_price == Decimal(1120)
    assert _reservation.rooms[0].netto_price_accepted == Decimal(6000)
    assert _reservation.rooms[0].price == Decimal(1120)
    assert _reservation.rooms[0].price_accepted == Decimal(6600)
    assert _reservation.rooms[0].tax == Decimal(600)
    assert _reservation.rooms[0].rate_plan_id == rate_plan.id
    assert _reservation.rooms[0].policy == {
        'name': 'Charge for 2 nights in case of cancelation',
        'policy_items': [{'days': None, 'charge': 2, 'charge_type': 'NIGHT'}]
    }
    assert _reservation.rooms[0].checkin == datetime.date.today()
    assert _reservation.rooms[0].checkout == datetime.date.today() + datetime.timedelta(days=5)

    for price in _reservation.rooms[1].day_prices:
        assert price.price_accepted == Decimal(1120)
        assert price.room_id is None
        assert price.roomtype_id == room_type.id
        assert price.tax == Decimal(0)

    assert _reservation.rooms[1].netto_price == Decimal(1120)
    assert _reservation.rooms[1].netto_price_accepted == Decimal(1120)
    assert _reservation.rooms[1].price == Decimal(1120)
    assert _reservation.rooms[1].price_accepted == Decimal(1120)
    assert _reservation.rooms[1].tax == Decimal(0)
    assert _reservation.rooms[1].rate_plan_id == 499
    assert _reservation.rooms[1].policy == {}
    assert _reservation.rooms[1].checkin == datetime.date.today()
    assert _reservation.rooms[1].checkout == datetime.date.today() + datetime.timedelta(days=3)

    assert _reservation.netto_price == Decimal(1120)
    assert _reservation.netto_price_accepted == Decimal(7120)
    assert _reservation.price == Decimal(1120)
    assert _reservation.price_accepted == Decimal(7720)
    assert _reservation.tax == Decimal(600)
    assert _reservation.checkin == datetime.date.today()
    assert _reservation.checkout == datetime.date.today() + datetime.timedelta(days=5)


def test_save_reservation_error(service: UpdateReservationPrices, context: Context, house, reservation):
    service._reservations_repo = Mock(save=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.reservation = reservation

    result = service.save_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_save_reservation_fail(service: UpdateReservationPrices, context: Context, house, reservation):
    service._reservations_repo = Mock(save=Mock(return_value=(Nothing, False)))
    context.house = house
    context.reservation = reservation

    result = service.save_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert result.failure().error.startswith('Error save prices for Reservation ID=')


def test_save_reservation_ok(service: UpdateReservationPrices, context: Context, house, reservation):
    _reservation = attr.evolve(reservation, price_accepted=Decimal(3600))
    service._reservations_repo = Mock(save=Mock(return_value=(Some(_reservation), True)))
    context.house = house
    context.reservation = reservation

    result = service.save_reservation(context)
    assert is_successful(result)
    assert result.unwrap().reservation == _reservation


def test_success(
    service: UpdateReservationPrices,
    context: Context,
    house,
    reservation,
    rate_plan,
    room_type,
    room,
    user,
    cancellation_policy,
):
    _reservation = attr.evolve(reservation, price_accepted=Decimal(3600))

    service._houses_repo = Mock(get=Mock(return_value=Some(house)))
    service._roomtypes_repo = Mock(select=Mock(return_value=[room_type]))
    service._rooms_repo = Mock(select=Mock(return_value=[room]))
    service._prices_repo = Mock(get_plan=Mock(return_value=Some(rate_plan)))
    service._reservations_repo = Mock(
        get=Mock(return_value=Some(reservation)), save=Mock(return_value=(Some(_reservation), True))
    )
    service._policies_repo = Mock(get=Mock(return_value=Some(cancellation_policy)))

    result = service.execute(
        house.id, reservation.id, reservation.rooms[0].id, rate_plan.id, user, prices=context.prices
    )
    assert is_successful(result)
    assert result.unwrap() == _reservation
