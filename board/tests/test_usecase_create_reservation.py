import datetime
from decimal import Decimal
from unittest.mock import Mock

import attr
import pytest
from django.utils import timezone
from returns.maybe import Nothing, Some
from returns.pipeline import is_successful

from board.entities import Reservation, ReservationDay, ReservationRoom
from board.usecases._create_reservation import Context, CreateReservation  # noqa
from board.value_objects import ReservationErrors, ReservationRequest
from effective_tours.constants import ReservationSources, ReservationStatuses


@pytest.fixture()
def service() -> CreateReservation:
    return CreateReservation()


@pytest.fixture()
def context(house, room_type, rate_plan, rate, user) -> Context:
    request = ReservationRequest(
        roomtype_id=room_type.id,
        plan_id=rate_plan.id,
        checkin=datetime.date.today(),
        checkout=datetime.date.today() + datetime.timedelta(days=2),
        guests=2,
        rate_id=rate.id,
        guest_name='John',
        guest_surname='Smith',
        guest_email='john@efft.com',
        guest_phone='+371-20202020',
        notes='Comment',
        prices={
            datetime.date.today(): Decimal(100),
            datetime.date.today() + datetime.timedelta(days=1): Decimal(110),
        },
    )
    return Context(house_id=house.id, request=request, user=user)


def test_missed_house_id(service: CreateReservation, context: Context):
    context.house_id = None

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_error(service: CreateReservation, context: Context):
    service._houses_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_house_fail(service: CreateReservation, context: Context):
    service._houses_repo = Mock(get=Mock(return_value=Nothing))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_ok(service: CreateReservation, context: Context, house):
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))

    result = service.select_house(context)
    assert is_successful(result)
    assert result.unwrap().house == house


def test_missed_reservation_request(service: CreateReservation, house, user):
    result = service.execute(house.id, None, user)  # noqa
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_missed_room_type(service: CreateReservation, context: Context, house):
    context.house = house
    context.request.roomtype_id = None

    result = service.select_room_type(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_roomtype


def test_select_room_type_error(service: CreateReservation, context: Context, house):
    service._roomtypes_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))
    context.house = house

    result = service.select_room_type(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_room_type_fail(service: CreateReservation, context: Context, house):
    service._roomtypes_repo = Mock(get=Mock(return_value=Nothing))
    context.house = house

    result = service.select_room_type(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_roomtype


def test_select_room_type_ok(service: CreateReservation, context: Context, house, room_type):
    service._roomtypes_repo = Mock(get=Mock(return_value=Some(room_type)))
    context.house = house

    result = service.select_room_type(context)
    assert is_successful(result)
    assert result.unwrap().room_type == room_type


def test_missed_rate_plan(service: CreateReservation, context: Context, house):
    context.house = house
    context.request.plan_id = None

    result = service.select_rate_plan(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_rateplan


def test_select_rate_plan_error(service: CreateReservation, context: Context, house):
    service._prices_repo = Mock(get_plan=Mock(side_effect=RuntimeError('ERR')))
    context.house = house

    result = service.select_rate_plan(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_rate_plan_fail(service: CreateReservation, context: Context, house):
    service._prices_repo = Mock(get_plan=Mock(return_value=Nothing))
    context.house = house

    result = service.select_rate_plan(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_rateplan


def test_select_rate_plan_ok(service: CreateReservation, context: Context, house, rate_plan):
    service._prices_repo = Mock(get_plan=Mock(return_value=Some(rate_plan)))
    context.house = house

    result = service.select_rate_plan(context)
    assert is_successful(result)
    assert result.unwrap().rate_plan == rate_plan


def test_select_rate_error(service: CreateReservation, context: Context, house, room_type, rate_plan):
    service._prices_repo = Mock(select_rates=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.room_type = room_type
    context.rate_plan = rate_plan

    result = service.select_rate(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_rate_fail(service: CreateReservation, context: Context, house, room_type, rate_plan):
    service._prices_repo = Mock(select_rates=Mock(return_value=[]))
    context.house = house
    context.room_type = room_type
    context.rate_plan = rate_plan

    result = service.select_rate(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_rate


def test_select_rate_ok(service: CreateReservation, context: Context, house, room_type, rate_plan, rate):
    rate_with_3 = attr.evolve(rate, id=401, occupancy=3)
    rate_with_4 = attr.evolve(rate, id=402, occupancy=4)
    service._prices_repo = Mock(select_rates=Mock(return_value=[rate_with_4, rate_with_3, rate]))
    context.house = house
    context.room_type = room_type
    context.rate_plan = rate_plan

    result = service.select_rate(context)
    assert is_successful(result)
    assert result.unwrap().rate == rate


def test_select_cancellation_policy_for_plan_without_policy(
    service: CreateReservation, context: Context, house, rate_plan
):
    context.rate_plan = attr.evolve(rate_plan, policy_id=0)
    context.house = house

    result = service.select_cancellation_policy(context)
    assert is_successful(result)
    assert result.unwrap().rate_plan.policy is None


def test_select_cancellation_policy_error(service: CreateReservation, context: Context, house, rate_plan):
    service._policies_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.rate_plan = rate_plan

    result = service.select_cancellation_policy(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_cancellation_policy_fail(service: CreateReservation, context: Context, house, rate_plan):
    service._policies_repo = Mock(get=Mock(return_value=Nothing))
    context.house = house
    context.rate_plan = rate_plan

    result = service.select_cancellation_policy(context)
    assert is_successful(result)
    assert result.unwrap().rate_plan.policy is None


def test_select_cancellation_policy_ok(
    service: CreateReservation, context: Context, house, rate_plan, cancellation_policy
):
    service._policies_repo = Mock(get=Mock(return_value=Some(cancellation_policy)))
    context.house = house
    context.rate_plan = rate_plan

    result = service.select_cancellation_policy(context)
    assert is_successful(result)
    assert result.unwrap().rate_plan.policy == cancellation_policy


def test_make_reservation_from_data(
    service: CreateReservation, context: Context, house, room_type, rate_plan, rate, cancellation_policy
):
    context.house = house
    context.room_type = room_type
    context.rate_plan = attr.evolve(rate_plan, policy=cancellation_policy)
    context.rate = rate

    result = service.make_reservation_from_date(context)
    assert is_successful(result)

    reservation = result.unwrap().reservation
    assert isinstance(reservation, Reservation)
    assert reservation.id is None
    assert reservation.house_id == house.id
    assert reservation.connection_id is None
    assert reservation.source == ReservationSources.MANUAL
    assert reservation.channel is None
    assert reservation.channel_id == ''
    assert reservation.checkin == context.request.checkin
    assert reservation.checkout == context.request.checkout
    assert reservation.status == ReservationStatuses.HOLD
    assert reservation.room_count == 1
    assert reservation.currency == house.currency.code
    assert reservation.price == Decimal(231)
    assert reservation.tax == Decimal(21)
    assert reservation.fees == Decimal(0)
    assert reservation.netto_price == Decimal(210)
    assert reservation.guest_name == 'John'
    assert reservation.guest_surname == 'Smith'
    assert reservation.guest_email == 'john@efft.com'
    assert reservation.guest_phone == '+371-20202020'

    assert len(reservation.rooms) == 1

    room = reservation.rooms[0]
    assert isinstance(room, ReservationRoom)
    assert room.id is None
    assert room.channel_id == ''
    assert room.channel_rate_id == ''
    assert room.checkin == context.request.checkin
    assert room.checkout == context.request.checkout
    assert room.rate_plan_id == rate_plan.id
    assert room.policy == {
        'name': 'Charge for 2 nights in case of cancelation',
        'policy_items': [{'days': None, 'charge': 2, 'charge_type': 'NIGHT'}]
    }
    assert room.rate_id == rate.id
    assert room.guest_name == 'John Smith'
    assert room.guest_count == 2
    assert room.adults == 2
    assert room.children == 0
    assert room.currency == house.currency.code
    assert room.price == Decimal(231)
    assert room.tax == Decimal(21)
    assert room.fees == Decimal(0)
    assert room.netto_price == Decimal(210)
    assert room.notes_info == 'Comment'

    assert len(room.day_prices) == 2

    price = room.day_prices[0]
    assert isinstance(price, ReservationDay)
    assert price.id is None
    assert price.day == context.request.checkin
    assert price.roomtype_id == room_type.id
    assert price.room_id is None
    assert price.price_changed == Decimal(100)
    assert price.price_original == Decimal(100)
    assert price.price_accepted == Decimal(100)
    assert price.tax == Decimal(10)
    assert price.currency == house.currency.code

    price = room.day_prices[1]
    assert isinstance(price, ReservationDay)
    assert price.id is None
    assert price.day == context.request.checkin + datetime.timedelta(days=1)
    assert price.roomtype_id == room_type.id
    assert price.room_id is None
    assert price.price_changed == Decimal(110)
    assert price.price_original == Decimal(110)
    assert price.price_accepted == Decimal(110)
    assert price.tax == Decimal(11)
    assert price.currency == house.currency.code


def test_make_reservation_from_data_no_prices(
    service: CreateReservation, context: Context, house, room_type, rate_plan, rate
):
    context.house = house
    context.room_type = room_type
    context.rate_plan = attr.evolve(rate_plan, policy=None)
    context.rate = rate
    context.request.prices = {}

    result = service.make_reservation_from_date(context)
    assert is_successful(result)

    reservation = result.unwrap().reservation
    assert isinstance(reservation, Reservation)
    assert reservation.id is None
    assert reservation.house_id == house.id
    assert reservation.connection_id is None
    assert reservation.source == ReservationSources.MANUAL
    assert reservation.channel is None
    assert reservation.channel_id == ''
    assert reservation.checkin == context.request.checkin
    assert reservation.checkout == context.request.checkout
    assert reservation.status == ReservationStatuses.HOLD
    assert reservation.room_count == 1
    assert reservation.currency == house.currency.code
    assert reservation.price == Decimal(0)
    assert reservation.tax == Decimal(0)
    assert reservation.fees == Decimal(0)
    assert reservation.netto_price == Decimal(0)
    assert reservation.guest_name == 'John'
    assert reservation.guest_surname == 'Smith'
    assert reservation.guest_email == 'john@efft.com'
    assert reservation.guest_phone == '+371-20202020'

    assert len(reservation.rooms) == 1

    room = reservation.rooms[0]
    assert isinstance(room, ReservationRoom)
    assert room.id is None
    assert room.channel_id == ''
    assert room.channel_rate_id == ''
    assert room.checkin == context.request.checkin
    assert room.checkout == context.request.checkout
    assert room.rate_plan_id == rate_plan.id
    assert room.policy == {}
    assert room.rate_id == rate.id
    assert room.guest_name == 'John Smith'
    assert room.guest_count == 2
    assert room.adults == 2
    assert room.children == 0
    assert room.currency == context.house.currency.code
    assert room.price == Decimal(0)
    assert room.tax == Decimal(0)
    assert room.fees == Decimal(0)
    assert room.netto_price == Decimal(0)
    assert room.notes_info == 'Comment'

    assert len(room.day_prices) == 2

    price = room.day_prices[0]
    assert isinstance(price, ReservationDay)
    assert price.id is None
    assert price.day == context.request.checkin
    assert price.roomtype_id == room_type.id
    assert price.room_id is None
    assert price.price_changed == Decimal(0)
    assert price.price_original == Decimal(0)
    assert price.price_accepted == Decimal(0)
    assert price.tax == Decimal(0)
    assert price.currency == house.currency.code

    price = room.day_prices[1]
    assert isinstance(price, ReservationDay)
    assert price.id is None
    assert price.day == context.request.checkin + datetime.timedelta(days=1)
    assert price.roomtype_id == room_type.id
    assert price.room_id is None
    assert price.price_changed == Decimal(0)
    assert price.price_original == Decimal(0)
    assert price.price_accepted == Decimal(0)
    assert price.tax == Decimal(0)
    assert price.currency == house.currency.code


def test_save_reservation_error(service: CreateReservation, context: Context, house, room_type, rate_plan):
    service._reservations_repo = Mock(save=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.room_type = room_type
    context.rate_plan = rate_plan
    context.reservation = Reservation(
        id=None,
        house_id=house.id,
        connection_id=None,
        source=ReservationSources.MANUAL,
        channel=None,
        channel_id='',
        checkin=context.request.checkin,
        checkout=context.request.checkout,
        booked_at=timezone.now(),
        status=ReservationStatuses.HOLD,
    )

    result = service.save_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_save_reservation_fail(service: CreateReservation, context: Context, house, room_type, rate_plan):
    service._reservations_repo = Mock(save=Mock(return_value=(Nothing, False)))
    context.house = house
    context.room_type = room_type
    context.rate_plan = rate_plan
    context.reservation = Reservation(
        id=None,
        house_id=house.id,
        connection_id=None,
        source=ReservationSources.MANUAL,
        channel=None,
        channel_id='',
        checkin=context.request.checkin,
        checkout=context.request.checkout,
        booked_at=timezone.now(),
        status=ReservationStatuses.HOLD,
    )

    result = service.save_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.save
    assert result.failure().error.startswith('Error save Reservation')


def test_save_reservation_ok(service: CreateReservation, context: Context, house, room_type, rate_plan):
    reservation = Reservation(
        id=111,
        house_id=house.id,
        connection_id=None,
        source=ReservationSources.MANUAL,
        channel=None,
        channel_id='',
        checkin=context.request.checkin,
        checkout=context.request.checkout,
        booked_at=timezone.now(),
        status=ReservationStatuses.HOLD,
    )
    service._reservations_repo = Mock(save=Mock(return_value=(Some(reservation), True)))
    context.house = house
    context.room_type = room_type
    context.rate_plan = rate_plan
    context.reservation = attr.evolve(reservation, id=None)

    result = service.save_reservation(context)
    assert is_successful(result)
    assert result.unwrap().reservation == reservation


def test_accept_reservation_error(service: CreateReservation, context: Context, house, room_type):
    service._reservations_repo = Mock(accept=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.room_type = room_type
    context.reservation = Reservation(
        id=111,
        house_id=house.id,
        connection_id=None,
        source=ReservationSources.MANUAL,
        channel=None,
        channel_id='',
        checkin=context.request.checkin,
        checkout=context.request.checkout,
        booked_at=timezone.now(),
        status=ReservationStatuses.HOLD,
    )

    result = service.accept_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_accept_reservation_fail(service: CreateReservation, context: Context, house, room_type):
    service._reservations_repo = Mock(accept=Mock(return_value=Nothing))
    context.house = house
    context.room_type = room_type
    context.reservation = Reservation(
        id=111,
        house_id=house.id,
        connection_id=None,
        source=ReservationSources.MANUAL,
        channel=None,
        channel_id='',
        checkin=context.request.checkin,
        checkout=context.request.checkout,
        booked_at=timezone.now(),
        status=ReservationStatuses.HOLD,
    )

    result = service.accept_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.save
    assert result.failure().error.startswith('Error accept new Reservation')


def test_accept_reservation_ok(service: CreateReservation, context: Context, house, room_type):
    reservation = Reservation(
        id=111,
        house_id=house.id,
        connection_id=None,
        source=ReservationSources.MANUAL,
        channel=None,
        channel_id='',
        checkin=context.request.checkin,
        checkout=context.request.checkout,
        booked_at=timezone.now(),
        status=ReservationStatuses.HOLD,
        is_verified=True,
    )
    service._reservations_repo = Mock(accept=Mock(return_value=Some(reservation)))
    context.house = house
    context.room_type = room_type
    context.reservation = attr.evolve(reservation, is_verified=False)

    result = service.accept_reservation(context)
    assert is_successful(result)
    assert result.unwrap().reservation == reservation


def test_success(
    service: CreateReservation, context: Context, house, room_type, rate_plan, rate, cancellation_policy
):
    reservation = Reservation(
        id=111,
        house_id=house.id,
        connection_id=None,
        source=ReservationSources.MANUAL,
        channel=None,
        channel_id='',
        checkin=context.request.checkin,
        checkout=context.request.checkout,
        booked_at=timezone.now(),
        status=ReservationStatuses.HOLD,
        is_verified=True,
    )
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))
    service._roomtypes_repo = Mock(get=Mock(return_value=Some(room_type)))
    service._prices_repo = Mock(get_plan=Mock(return_value=Some(rate_plan)), select_rates=Mock(return_value=[rate]))
    service._reservations_repo = Mock(
        save=Mock(return_value=(Some(attr.evolve(reservation, is_verified=False)), True)),
        accept=Mock(return_value=Some(reservation)),
    )
    service._policies_repo = Mock(get=Mock(return_value=Some(cancellation_policy)))

    result = service.execute(house.id, context.request, context.user)
    assert is_successful(result), result.failure()
    assert result.unwrap() == attr.evolve(reservation, is_verified=True)
