import datetime
from decimal import Decimal
from unittest.mock import Mock

import attr
import pytest
from django.utils import timezone
from returns.maybe import Nothing, Some
from returns.pipeline import is_successful

from board.entities import Reservation, ReservationDay, ReservationRoom
from board.usecases._accept_reservation_changes import AcceptReservationChanges, Context  # noqa
from board.value_objects import ReservationErrors
from channels.entities import Connection, RatePlanMapping, RoomConnection
from effective_tours.constants import Channels, ConnectionStatuses, ReservationSources, ReservationStatuses


@pytest.fixture()
def service() -> AcceptReservationChanges:
    return AcceptReservationChanges()


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
        channel_id='1697441495',
        checkin=checkin,
        checkout=checkout,
        booked_at=timezone.now(),
        status=ReservationStatuses.MODIFY,
        is_verified=False,
        guest_name='John',
        guest_surname='Smith',
        guest_phone='+1-222-3344',
        price=Decimal(1120),
        netto_price=Decimal(1120),
        rooms=[
            ReservationRoom(
                id=211,
                reservation_id=111,
                channel_id=room_connection.channel_id,
                channel_rate_id='',
                checkin=checkin,
                checkout=checkout,
                rate_plan_id=rate_plan_mapping.rate_plan_id,
                rate_plan_id_original=rate_plan_mapping.rate_plan_id,
                policy={'name': 'NEW POLICY'},
                policy_original={'name': 'OLD POLICY'},
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
                        price_changed=Decimal(1220),
                        currency=house.currency.code,
                    ),
                    ReservationDay(
                        id=312,
                        reservation_room_id=211,
                        day=checkin + datetime.timedelta(days=1),
                        roomtype_id=room_connection.roomtype_id,
                        price_original=Decimal(1120),
                        price_accepted=Decimal(1120),
                        price_changed=Decimal(1220),
                        currency=house.currency.code,
                    ),
                    ReservationDay(
                        id=313,
                        reservation_room_id=211,
                        day=checkin + datetime.timedelta(days=2),
                        roomtype_id=room_connection.roomtype_id,
                        price_original=Decimal(1120),
                        price_accepted=Decimal(1120),
                        price_changed=Decimal(1220),
                        currency=house.currency.code,
                    ),
                ],
            )
        ],
    )


@pytest.fixture()
def context(house, reservation, user) -> Context:
    return Context(house_id=house.id, pk=reservation.id, user=user, price_ids=[311, 313])


def test_missed_house_id(service: AcceptReservationChanges, context: Context):
    context.house_id = None

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_error(service: AcceptReservationChanges, context: Context):
    service._houses_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_house_fail(service: AcceptReservationChanges, context: Context):
    service._houses_repo = Mock(get=Mock(return_value=Nothing))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_ok(service: AcceptReservationChanges, context: Context, house):
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))

    result = service.select_house(context)
    assert is_successful(result)
    assert result.unwrap().house == house


def test_select_reservation_missed_pk(service: AcceptReservationChanges, context: Context, house):
    context.house = house
    context.pk = None

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_error(service: AcceptReservationChanges, context: Context, house):
    service._reservations_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_reservation_fail(service: AcceptReservationChanges, context: Context, house):
    service._reservations_repo = Mock(get=Mock(return_value=Nothing))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_ok(service: AcceptReservationChanges, context: Context, house, reservation):
    service._reservations_repo = Mock(get=Mock(return_value=Some(reservation)))
    context.house = house

    result = service.select_reservation(context)
    assert is_successful(result)
    assert result.unwrap().source == reservation


def test_check_reservation_wrong_house(service: AcceptReservationChanges, context: Context, house, reservation):
    context.house = house
    context.source = attr.evolve(reservation, house_id=999)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_check_reservation_room_close(service: AcceptReservationChanges, context: Context, house, reservation):
    context.house = house
    context.source = attr.evolve(reservation, status=ReservationStatuses.CLOSE)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_check_reservation_canceled(service: AcceptReservationChanges, context: Context, house, reservation):
    context.house = house
    context.source = attr.evolve(reservation, status=ReservationStatuses.CANCEL)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_check_reservation_manual(service: AcceptReservationChanges, context: Context, house, reservation):
    context.house = house
    context.source = attr.evolve(reservation, source=ReservationSources.MANUAL)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_check_reservation_verified(service: AcceptReservationChanges, context: Context, house, reservation):
    context.house = house
    context.source = attr.evolve(reservation, is_verified=True)

    result = service.check_reservation(context)
    assert is_successful(result)


def test_check_reservation_ok(service: AcceptReservationChanges, context: Context, house, reservation):
    context.house = house
    context.source = reservation

    result = service.check_reservation(context)
    assert is_successful(result)


def test_accept_changes_for_verified(service: AcceptReservationChanges, context: Context, house, reservation):
    _reservation = attr.evolve(reservation, is_verified=True)
    service._reservations_repo = Mock(accept=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.source = _reservation

    result = service.accept_changes(context)
    assert is_successful(result)
    assert result.unwrap().reservation == _reservation


def test_accept_changes_error(service: AcceptReservationChanges, context: Context, house, reservation):
    service._reservations_repo = Mock(accept=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.source = reservation

    result = service.accept_changes(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_accept_changes_fail(service: AcceptReservationChanges, context: Context, house, reservation):
    service._reservations_repo = Mock(accept=Mock(return_value=Nothing))
    context.house = house
    context.source = reservation

    result = service.accept_changes(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert result.failure().error.startswith('Error accept changes for Reservation ID=')


def test_accept_changes_ok(service: AcceptReservationChanges, context: Context, house, reservation):
    _reservation = attr.evolve(reservation, is_verified=True)
    service._reservations_repo = Mock(accept=Mock(return_value=Some(_reservation)))
    context.house = house
    context.source = reservation

    result = service.accept_changes(context)
    assert is_successful(result)
    assert result.unwrap().reservation == _reservation


def test_success(service: AcceptReservationChanges, house, reservation, user):
    _reservation = attr.evolve(reservation, is_verified=True)
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))
    service._reservations_repo = Mock(
        get=Mock(return_value=Some(reservation)), accept=Mock(return_value=Some(_reservation))
    )

    result = service.execute(house.id, reservation.id, user, price_ids=[311, 313])
    assert is_successful(result)
    assert result.unwrap() == _reservation
