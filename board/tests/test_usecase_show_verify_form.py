import datetime
from decimal import Decimal
from unittest.mock import Mock

import attr
import pytest
from django.utils import timezone
from returns.maybe import Nothing, Some
from returns.pipeline import is_successful

from board.entities import Reservation, ReservationDay, ReservationRoom
from board.usecases._show_verify_form import Context, ShowVerifyForm  # noqa
from board.value_objects import ReservationErrors, ReservationVerifyContext
from channels.entities import Connection, RatePlanMapping, RoomConnection
from effective_tours.constants import Channels, ConnectionStatuses, ReservationSources, ReservationStatuses


@pytest.fixture()
def service() -> ShowVerifyForm:
    return ShowVerifyForm()


@pytest.fixture(scope='module')
def connection(house):
    return Connection(
        id=1, house_id=house.id, channel=Channels.EXPEDIA, property_id='148832', activity=ConnectionStatuses.ACTIVE
    )


@pytest.fixture(scope='module')
def room_connection(connection, room_type):
    return RoomConnection(
        id=2,
        connection=connection,
        roomtype_id=room_type.id,
        channel_id='215832731',
        activity=ConnectionStatuses.ACTIVE,
    )


@pytest.fixture(scope='module')
def rate_plan_mapping(room_connection, rate_plan):
    return RatePlanMapping(
        id=3, room_connection=room_connection, rate_plan_id=rate_plan.id, channel_id='258285468A', occupancy=2
    )


@pytest.fixture(scope='module')
def reservation(house, connection, room_connection, rate_plan_mapping):
    checkin = datetime.date.today()
    checkout = checkin + datetime.timedelta(days=3)
    return Reservation(
        id=111,
        house_id=house.id,
        connection_id=connection.id,
        source=ReservationSources.EXPEDIA,
        channel=Channels.EXPEDIA,
        channel_id="1697441495",
        checkin=checkin,
        checkout=checkout,
        booked_at=timezone.now(),
        status=ReservationStatuses.MODIFY,
        is_verified=False,
        guest_name="John",
        guest_surname="Smith",
        guest_phone="+1-222-3344",
        price=Decimal(1120),
        netto_price=Decimal(1120),
        rooms=[
            ReservationRoom(
                id=211,
                reservation_id=111,
                channel_id=room_connection.channel_id,
                channel_rate_id="",
                checkin=checkin,
                checkout=checkout,
                rate_plan_id=rate_plan_mapping.rate_plan_id,
                rate_plan_id_original=rate_plan_mapping.rate_plan_id,
                adults=2,
                children=1,
                price=Decimal(1120),
                netto_price=Decimal(1120),
                day_prices=[
                    ReservationDay(
                        id=311,
                        reservation_room_id=211,
                        day=checkin,
                        roomtype_id=room_connection.roomtype_id,
                        price_original=Decimal(1120),
                        price_accepted=Decimal(1120),
                        currency=house.currency.code,
                    ),
                    ReservationDay(
                        id=312,
                        reservation_room_id=211,
                        day=checkin + datetime.timedelta(days=1),
                        roomtype_id=room_connection.roomtype_id,
                        price_original=Decimal(1120),
                        price_accepted=Decimal(1120),
                        currency=house.currency.code,
                    ),
                    ReservationDay(
                        id=313,
                        reservation_room_id=211,
                        day=checkin + datetime.timedelta(days=2),
                        roomtype_id=room_connection.roomtype_id,
                        price_original=Decimal(1120),
                        price_accepted=Decimal(1120),
                        currency=house.currency.code,
                    ),
                ],
            )
        ],
    )


@pytest.fixture()
def context(house, reservation, user) -> Context:
    return Context(house_id=house.id, pk=reservation.id, user=user)


def test_missed_house_id(service: ShowVerifyForm, context: Context):
    context.house_id = None

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_error(service: ShowVerifyForm, context: Context):
    service._houses_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_house_fail(service: ShowVerifyForm, context: Context):
    service._houses_repo = Mock(get=Mock(return_value=Nothing))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_ok(service: ShowVerifyForm, context: Context, house):
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))

    result = service.select_house(context)
    assert is_successful(result)
    assert result.unwrap().house == house


def test_select_reservation_missed_pk(service: ShowVerifyForm, context: Context, house):
    context.house = house
    context.pk = None

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_error(service: ShowVerifyForm, context: Context, house):
    service._reservations_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_reservation_fail(service: ShowVerifyForm, context: Context, house):
    service._reservations_repo = Mock(get=Mock(return_value=Nothing))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_ok(service: ShowVerifyForm, context: Context, house, reservation):
    service._reservations_repo = Mock(get=Mock(return_value=Some(reservation)))
    context.house = house

    result = service.select_reservation(context)
    assert is_successful(result)
    assert result.unwrap().reservation == reservation


def test_check_reservation_wrong_house(service: ShowVerifyForm, context: Context, house, reservation):
    context.house = house
    context.reservation = attr.evolve(reservation, house_id=999)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_check_reservation_room_close(service: ShowVerifyForm, context: Context, house, reservation):
    context.house = house
    context.reservation = attr.evolve(reservation, status=ReservationStatuses.CLOSE)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_check_reservation_canceled(service: ShowVerifyForm, context: Context, house, reservation):
    context.house = house
    context.reservation = attr.evolve(reservation, status=ReservationStatuses.CANCEL)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_check_reservation_manual(service: ShowVerifyForm, context: Context, house, reservation):
    context.house = house
    context.reservation = attr.evolve(reservation, source=ReservationSources.MANUAL)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_check_reservation_ok(service: ShowVerifyForm, context: Context, house, reservation):
    context.house = house
    context.reservation = reservation

    result = service.check_reservation(context)
    assert is_successful(result), result.failure()


def test_populate_with_plans_error(service: ShowVerifyForm, context: Context, house, reservation):
    service._prices_repo = Mock(select_plans=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.reservation = reservation

    result = service.populate_with_plans(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_populate_with_plans_ok(service: ShowVerifyForm, context: Context, house, reservation, rate_plan):
    service._prices_repo = Mock(select_plans=Mock(return_value=[rate_plan]))
    context.house = house
    context.reservation = reservation

    result = service.populate_with_plans(context)
    assert is_successful(result)
    assert result.unwrap().reservation.rooms[0].rate_plan == rate_plan
    assert result.unwrap().reservation.rooms[0].rate_plan_original == rate_plan


def test_populate_with_room_types_error(service: ShowVerifyForm, context: Context, house, reservation):
    service._roomtypes_repo = Mock(select=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.reservation = reservation

    result = service.populate_with_room_types(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_populate_with_room_types_ok(service: ShowVerifyForm, context: Context, house, reservation, room_type):
    service._roomtypes_repo = Mock(select=Mock(return_value=[room_type]))
    context.house = house
    context.reservation = reservation

    result = service.populate_with_room_types(context)
    assert is_successful(result)
    for room in result.unwrap().reservation.rooms:
        for price in room.day_prices:
            assert price.room_type == room_type


def test_success(service: ShowVerifyForm, context: Context, house, reservation, user, rate_plan, room_type):
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))
    service._reservations_repo = Mock(get=Mock(return_value=Some(reservation)))
    service._prices_repo = Mock(select_plans=Mock(return_value=[rate_plan]))
    service._roomtypes_repo = Mock(select=Mock(return_value=[room_type]))

    result = service.execute(house.id, reservation.id, user)
    assert is_successful(result)

    ctx = result.unwrap()
    assert isinstance(ctx, ReservationVerifyContext)
    assert ctx.house == house
    assert ctx.reservation == reservation
