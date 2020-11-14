import datetime
from decimal import Decimal
from unittest.mock import Mock

import attr
import pytest
from django.utils import timezone
from returns.maybe import Nothing, Some
from returns.pipeline import is_successful

from board.entities import Reservation, ReservationDay, ReservationRoom
from board.usecases._show_prices_form import Context, ShowPricesForm  # noqa
from board.value_objects import ReservationErrors, ReservationPricesUpdateContext
from cancelations.entities import Policy
from channels.entities import Connection, RatePlanMapping, RoomConnection
from effective_tours.constants import Channels, ConnectionStatuses, ReservationSources, ReservationStatuses


@pytest.fixture()
def service() -> ShowPricesForm:
    return ShowPricesForm()


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
    return Context(house_id=house.id, pk=reservation.id, room_id=reservation.rooms[0].id, user=user)


def test_missed_house_id(service: ShowPricesForm, context: Context):
    context.house_id = None

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_error(service: ShowPricesForm, context: Context):
    service._houses_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_house_fail(service: ShowPricesForm, context: Context):
    service._houses_repo = Mock(get=Mock(return_value=Nothing))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_ok(service: ShowPricesForm, context: Context, house):
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))

    result = service.select_house(context)
    assert is_successful(result)
    assert result.unwrap().house == house


def test_select_reservation_missed_pk(service: ShowPricesForm, context: Context, house):
    context.house = house
    context.pk = None

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_error(service: ShowPricesForm, context: Context, house):
    service._reservations_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_reservation_fail(service: ShowPricesForm, context: Context, house):
    service._reservations_repo = Mock(get=Mock(return_value=Nothing))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_ok(service: ShowPricesForm, context: Context, house, reservation):
    service._reservations_repo = Mock(get=Mock(return_value=Some(reservation)))
    context.house = house

    result = service.select_reservation(context)
    assert is_successful(result)
    assert result.unwrap().reservation == reservation


def test_check_reservation_wrong_house(service: ShowPricesForm, context: Context, house, reservation):
    context.house = house
    context.reservation = attr.evolve(reservation, house_id=999)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_check_reservation_room_close(service: ShowPricesForm, context: Context, house, reservation):
    context.house = house
    context.reservation = attr.evolve(reservation, status=ReservationStatuses.CLOSE)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_check_reservation_canceled(service: ShowPricesForm, context: Context, house, reservation):
    context.house = house
    context.reservation = attr.evolve(reservation, status=ReservationStatuses.CANCEL)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_room_missed_id(service: ShowPricesForm, context: Context, house, reservation):
    context.house = house
    context.reservation = reservation
    context.room_id = None

    result = service.select_reservation_room(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_room_wrong_id(service: ShowPricesForm, context: Context, house, reservation):
    context.house = house
    context.reservation = reservation
    context.room_id = 999

    result = service.select_reservation_room(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_room_ok(service: ShowPricesForm, context: Context, house, reservation):
    context.house = house
    context.reservation = reservation

    result = service.select_reservation_room(context)
    assert is_successful(result)
    assert result.unwrap().reservation_room == reservation.rooms[0]


def test_select_rate_plans_error(service: ShowPricesForm, context: Context, house):
    service._prices_repo = Mock(select_plans=Mock(side_effect=RuntimeError('ERR')))
    context.house = house

    result = service.select_rate_plans(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_rate_plans_ok(service: ShowPricesForm, context: Context, house, rate_plan):
    service._prices_repo = Mock(select_plans=Mock(return_value=[rate_plan]))
    context.house = house

    result = service.select_rate_plans(context)
    assert is_successful(result)
    assert result.unwrap().rate_plans == [rate_plan]


def test_select_cancellation_policies_error(service: ShowPricesForm, context: Context, house):
    service._policies_repo = Mock(select=Mock(side_effect=RuntimeError('ERR')))
    context.house = house

    result = service.select_cancellation_policies(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_cancellation_policies_ok(service: ShowPricesForm, context: Context, house):
    policy_1 = Policy(id=101, house_id=house.id, name='P1')
    policy_2 = Policy(id=102, house_id=house.id, name='P2')
    service._policies_repo = Mock(select=Mock(return_value=[policy_1, policy_2]))
    context.house = house

    result = service.select_cancellation_policies(context)
    assert is_successful(result)
    assert result.unwrap().policies == [policy_1, policy_2]


def test_select_room_types_error(service: ShowPricesForm, context: Context, house):
    service._roomtypes_repo = Mock(select=Mock(side_effect=RuntimeError('ERR')))
    context.house = house

    result = service.select_room_types(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_room_types_ok(service: ShowPricesForm, context: Context, house, room_type):
    service._roomtypes_repo = Mock(select=Mock(return_value=[room_type]))
    context.house = house

    result = service.select_room_types(context)
    assert is_successful(result)
    assert result.unwrap().room_types == [room_type]


def test_select_rooms_error(service: ShowPricesForm, context: Context, house):
    service._rooms_repo = Mock(select=Mock(side_effect=RuntimeError('ERR')))
    context.house = house

    result = service.select_rooms(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_rooms_ok(service: ShowPricesForm, context: Context, house, room):
    service._rooms_repo = Mock(select=Mock(return_value=[room]))
    context.house = house

    result = service.select_rooms(context)
    assert is_successful(result)
    assert result.unwrap().rooms == [room]


def test_success(service: ShowPricesForm, house, reservation, user, rate_plan, room_type, room):
    policy_1 = Policy(id=101, house_id=house.id, name='P1')
    policy_2 = Policy(id=102, house_id=house.id, name='P2')

    service._houses_repo = Mock(get=Mock(return_value=Some(house)))
    service._reservations_repo = Mock(get=Mock(return_value=Some(reservation)))
    service._prices_repo = Mock(select_plans=Mock(return_value=[rate_plan]))
    service._roomtypes_repo = Mock(select=Mock(return_value=[room_type]))
    service._rooms_repo = Mock(select=Mock(return_value=[room]))
    service._policies_repo = Mock(select=Mock(return_value=[policy_1, policy_2]))

    result = service.execute(house.id, reservation.id, reservation.rooms[0].id, user)
    assert is_successful(result)

    ctx = result.unwrap()
    assert isinstance(ctx, ReservationPricesUpdateContext)
    assert ctx.house == house
    assert ctx.reservation == reservation
    assert ctx.reservation_room == reservation.rooms[0]
    assert ctx.rate_plans == [rate_plan]
    assert ctx.room_types == [room_type]
    assert ctx.rooms == [room]
    assert ctx.policies == [policy_1, policy_2]
