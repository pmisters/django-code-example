import datetime
from unittest.mock import Mock

import attr
import pytest
from django.utils import timezone
from returns.maybe import Nothing, Some
from returns.pipeline import is_successful

from board.entities import Reservation
from board.usecases._attach_contact_to_reservation import AttachContactToReservation, Context
from board.value_objects import ReservationErrors
from effective_tours.constants import ReservationSources, ReservationStatuses


@pytest.fixture()
def service() -> AttachContactToReservation:
    return AttachContactToReservation()


@pytest.fixture(scope="module")
def reservation(house, rate_plan, room_type):
    checkin = datetime.date.today()
    checkout = checkin + datetime.timedelta(days=3)
    return Reservation(
        id=111,
        house_id=house.id,
        connection_id=None,
        source=ReservationSources.MANUAL,
        channel=None,
        channel_id="",
        checkin=checkin,
        checkout=checkout,
        booked_at=timezone.now(),
        status=ReservationStatuses.NEW,
    )


@pytest.fixture()
def context(house, reservation) -> Context:
    return Context(house_id=house.id, pk=reservation.id, contact_id=200)


def test_missed_house_id(service: AttachContactToReservation, context: Context):
    context.house_id = None

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_error(service: AttachContactToReservation, context: Context):
    service._houses_repo = Mock(get=Mock(side_effect=RuntimeError("ERR")))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_house_fail(service: AttachContactToReservation, context: Context):
    service._houses_repo = Mock(get=Mock(return_value=Nothing))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_ok(service: AttachContactToReservation, context: Context, house):
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))

    result = service.select_house(context)
    assert is_successful(result), result.failure()
    assert result.unwrap().house == house


def test_missed_reservation_id(service: AttachContactToReservation, context: Context, house):
    context.house = house
    context.pk = None

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_error(service: AttachContactToReservation, context: Context, house):
    service._reservations_repo = Mock(get=Mock(side_effect=RuntimeError("ERR")))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_reservation_fail(service: AttachContactToReservation, context: Context, house):
    service._reservations_repo = Mock(get=Mock(return_value=Nothing))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_ok(service: AttachContactToReservation, context: Context, house, reservation):
    service._reservations_repo = Mock(get=Mock(return_value=Some(reservation)))
    context.house = house

    result = service.select_reservation(context)
    assert is_successful(result)
    assert result.unwrap().reservation == reservation


def test_check_reservation_room_close(service: AttachContactToReservation, context: Context, house, reservation):
    context.house = house
    context.reservation = attr.evolve(reservation, status=ReservationStatuses.CLOSE)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_check_reservation_ok(service: AttachContactToReservation, context: Context, house, reservation):
    context.house = house
    context.reservation = reservation

    result = service.check_reservation(context)
    assert is_successful(result)


def test_add_contact_first(service: AttachContactToReservation, context: Context, reservation):
    context.reservation = attr.evolve(reservation, guest_contact_id=None, guest_contact_ids=[])

    result = service.add_contact(context)
    assert is_successful(result)
    assert result.unwrap().reservation.guest_contact_id == 200
    assert result.unwrap().reservation.guest_contact_ids == [200]


def test_add_contact_not_first(service: AttachContactToReservation, context: Context, reservation):
    context.reservation = attr.evolve(reservation, guest_contact_id=10, guest_contact_ids=[10])

    result = service.add_contact(context)
    assert is_successful(result)
    assert result.unwrap().reservation.guest_contact_id == 10
    assert result.unwrap().reservation.guest_contact_ids == [10, 200]


def test_add_contact_duplicated(service: AttachContactToReservation, context: Context, reservation):
    context.reservation = attr.evolve(reservation, guest_contact_id=10, guest_contact_ids=[10, 200])

    result = service.add_contact(context)
    assert is_successful(result)
    assert result.unwrap().reservation.guest_contact_id == 10
    assert result.unwrap().reservation.guest_contact_ids == [10, 200]


def test_save_error(service: AttachContactToReservation, context: Context, house, reservation):
    service._reservations_repo = Mock(save=Mock(side_effect=RuntimeError("ERR")))
    context.house = house
    context.reservation = reservation

    result = service.save(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_save_fail(service: AttachContactToReservation, context: Context, house, reservation):
    service._reservations_repo = Mock(save=Mock(return_value=(Nothing, False)))
    context.house = house
    context.reservation = reservation

    result = service.save(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.save
    assert result.failure().error.startswith("Error save Reservation")


def test_save_reservation_ok(service: AttachContactToReservation, context: Context, house, reservation):
    _reservation = attr.evolve(reservation, guest_contact_id=200, guest_contact_ids=[200])
    service._reservations_repo = Mock(save=Mock(return_value=(Some(_reservation), True)))
    context.house = house
    context.reservation = reservation

    result = service.save(context)
    assert is_successful(result)
    assert result.unwrap().reservation == _reservation


def test_success(service: AttachContactToReservation, context: Context, house, reservation):
    _reservation = attr.evolve(reservation, guest_contact_id=200, guest_contact_ids=[200])
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))
    service._reservations_repo = Mock(
        get=Mock(return_value=Some(reservation)), save=Mock(return_value=(Some(_reservation), True))
    )

    result = service.execute(house.id, reservation.id, 200)
    assert is_successful(result)
    assert result.unwrap()
