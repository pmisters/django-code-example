import datetime
from decimal import Decimal
from unittest.mock import Mock

import attr
import pytest
from django.utils import timezone
from returns.maybe import Nothing, Some
from returns.pipeline import is_successful

from board.entities import Reservation
from board.usecases._update_reservation_guest import Context, UpdateReservationGuest  # noqa
from board.value_objects import ReservationErrors
from effective_tours.constants import ReservationSources, ReservationStatuses


@pytest.fixture()
def service() -> UpdateReservationGuest:
    return UpdateReservationGuest()


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
        guest_name='TEST',
        guest_surname='Some',
        guest_email='test@test.com',
        guest_phone='12345',
        guest_contact_id=11,
    )


@pytest.fixture()
def context(house, reservation) -> Context:
    return Context(house_id=house.id, pk=reservation.id, contact_id=11, attribute='name', value='John Smith')


def test_missed_house_id(service: UpdateReservationGuest, context: Context):
    context.house_id = None

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_error(service: UpdateReservationGuest, context: Context):
    service._houses_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_house_fail(service: UpdateReservationGuest, context: Context):
    service._houses_repo = Mock(get=Mock(return_value=Nothing))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_ok(service: UpdateReservationGuest, context: Context, house):
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))

    result = service.select_house(context)
    assert is_successful(result)
    assert result.unwrap().house == house


def test_select_reservation_missed_pk(service: UpdateReservationGuest, context: Context, house):
    context.house = house
    context.pk = None

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_error(service: UpdateReservationGuest, context: Context, house):
    service._reservations_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_reservation_fail(service: UpdateReservationGuest, context: Context, house):
    service._reservations_repo = Mock(get=Mock(return_value=Nothing))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_ok(service: UpdateReservationGuest, context: Context, house, reservation):
    service._reservations_repo = Mock(get=Mock(return_value=Some(reservation)))
    context.house = house

    result = service.select_reservation(context)
    assert is_successful(result)
    assert result.unwrap().source == reservation


def test_check_reservation_wrong_house(service: UpdateReservationGuest, context: Context, house, reservation):
    context.house = house
    context.source = attr.evolve(reservation, house_id=999)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_check_reservation_room_close(service: UpdateReservationGuest, context: Context, house, reservation):
    context.house = house
    context.source = attr.evolve(reservation, status=ReservationStatuses.CLOSE)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_check_reservation_ota(service: UpdateReservationGuest, context: Context, house, reservation):
    context.house = house
    context.source = attr.evolve(reservation, source=ReservationSources.BOOKING)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_missed_contact_id(service: UpdateReservationGuest, house, reservation):
    result = service.execute(house.id, reservation.id, None, 'name', 'John Smith')  # noqa
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert result.failure().error.startswith('Missed Contact ID for update Guest information')


def test_missed_attribute_name(service: UpdateReservationGuest, house, reservation):
    result = service.execute(house.id, reservation.id, 11, None, 'John Smith')  # noqa
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert result.failure().error.startswith('Missed attribute for update Guest information')


def test_unsupported_guest_attribute(service: UpdateReservationGuest, house, reservation):
    result = service.execute(house.id, reservation.id, 11, 'guest_city', 'London')
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert result.failure().error.startswith('Unsupported attribute [guest_city] for update Guest information')


def test_make_reservation_from_data_other_guest(
    service: UpdateReservationGuest, context: Context, house, reservation
):
    context.contact_id = 999
    context.house = house
    context.source = reservation

    result = service.make_reservation_from_data(context)
    assert is_successful(result)

    _reservation = result.unwrap().reservation
    assert _reservation.guest_name == 'TEST'
    assert _reservation.guest_surname == 'Some'
    assert _reservation.guest_email == 'test@test.com'
    assert _reservation.guest_phone == '12345'


def test_make_reservation_from_data_name(service: UpdateReservationGuest, context: Context, house, reservation):
    context.house = house
    context.source = reservation

    result = service.make_reservation_from_data(context)
    assert is_successful(result)

    _reservation = result.unwrap().reservation
    assert _reservation.guest_name == 'John'
    assert _reservation.guest_surname == 'Smith'
    assert _reservation.guest_email == 'test@test.com'
    assert _reservation.guest_phone == '12345'


def test_make_reservation_from_data_email(service: UpdateReservationGuest, context: Context, house, reservation):
    context.attribute = 'email'
    context.value = 'et@efft.com'
    context.house = house
    context.source = reservation

    result = service.make_reservation_from_data(context)
    assert is_successful(result)

    _reservation = result.unwrap().reservation
    assert _reservation.guest_name == 'TEST'
    assert _reservation.guest_surname == 'Some'
    assert _reservation.guest_email == 'et@efft.com'
    assert _reservation.guest_phone == '12345'


def test_make_reservation_from_data_phone(service: UpdateReservationGuest, context: Context, house, reservation):
    context.attribute = 'phone'
    context.value = '+123123123'
    context.house = house
    context.source = reservation

    result = service.make_reservation_from_data(context)
    assert is_successful(result)

    _reservation = result.unwrap().reservation
    assert _reservation.guest_name == 'TEST'
    assert _reservation.guest_surname == 'Some'
    assert _reservation.guest_email == 'test@test.com'
    assert _reservation.guest_phone == '+123123123'


def test_save_reservation_error(service: UpdateReservationGuest, context: Context, house, reservation):
    service._reservations_repo = Mock(save=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.source = reservation
    context.reservation = reservation

    result = service.save_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_save_reservation_fail(service: UpdateReservationGuest, context: Context, house, reservation):
    service._reservations_repo = Mock(save=Mock(return_value=(Nothing, False)))
    context.house = house
    context.source = reservation
    context.reservation = reservation

    result = service.save_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert result.failure().error.startswith('Error save guest information for Reservation ID=')


def test_save_reservation_ok(service: UpdateReservationGuest, context: Context, house, reservation):
    _reservation = attr.evolve(reservation, guest_name='John')
    service._reservations_repo = Mock(save=Mock(return_value=(Some(_reservation), True)))
    context.house = house
    context.source = reservation
    context.reservation = reservation

    result = service.save_reservation(context)
    assert is_successful(result)
    assert result.unwrap().reservation == _reservation


def test_save_reservation_other_guest(service: UpdateReservationGuest, context: Context, house, reservation):
    service._reservations_repo = Mock(save=Mock(side_effect=RuntimeError('ERR')))
    context.contact_id = 999
    context.house = house
    context.source = reservation
    context.reservation = reservation

    result = service.save_reservation(context)
    assert is_successful(result)
    assert result.unwrap().reservation == reservation


def test_success(service: UpdateReservationGuest, house, reservation):
    _reservation = attr.evolve(reservation, guest_name='John')
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))
    service._reservations_repo = Mock(
        get=Mock(return_value=Some(reservation)), save=Mock(return_value=(Some(_reservation), True))
    )

    result = service.execute(house.id, reservation.id, 11, 'name', 'John Smith')
    assert is_successful(result)
    assert result.unwrap() == _reservation
