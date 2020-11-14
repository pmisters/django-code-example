import datetime
from unittest.mock import Mock

import attr
import pytest
from django.utils import timezone
from returns.maybe import Nothing, Some
from returns.pipeline import is_successful

from board.entities import Reservation
from board.usecases._accept_hold_reservation import AcceptHoldReservation, Context  # noqa
from board.value_objects import ReservationErrors
from effective_tours.constants import ReservationSources, ReservationStatuses


@pytest.fixture()
def service() -> AcceptHoldReservation:
    return AcceptHoldReservation()


@pytest.fixture(scope='module')
def reservation(house):
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
        status=ReservationStatuses.HOLD,
        is_verified=True,
        quotation_id=123
    )


@pytest.fixture()
def context(house, reservation, user) -> Context:
    return Context(house_id=house.id, pk=reservation.id, user=user)


def test_missed_house_id(service: AcceptHoldReservation, context: Context):
    context.house_id = None

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_error(service: AcceptHoldReservation, context: Context):
    service._houses_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_house_fail(service: AcceptHoldReservation, context: Context):
    service._houses_repo = Mock(get=Mock(return_value=Nothing))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_ok(service: AcceptHoldReservation, context: Context, house):
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))

    result = service.select_house(context)
    assert is_successful(result)
    assert result.unwrap().house == house


def test_select_reservation_missed_pk(service: AcceptHoldReservation, context: Context, house):
    context.house = house
    context.pk = None

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_error(service: AcceptHoldReservation, context: Context, house):
    service._reservations_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_reservation_fail(service: AcceptHoldReservation, context: Context, house):
    service._reservations_repo = Mock(get=Mock(return_value=Nothing))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_ok(service: AcceptHoldReservation, context: Context, house, reservation):
    service._reservations_repo = Mock(get=Mock(return_value=Some(reservation)))
    context.house = house

    result = service.select_reservation(context)
    assert is_successful(result)
    assert result.unwrap().source == reservation


def test_check_reservation_room_close(service: AcceptHoldReservation, context: Context, house, reservation):
    context.house = house
    context.source = attr.evolve(reservation, status=ReservationStatuses.CLOSE)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_check_reservation_ota(service: AcceptHoldReservation, context: Context, house, reservation):
    context.house = house
    context.source = attr.evolve(reservation, source=ReservationSources.BOOKING)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_check_reservation_accepted(service: AcceptHoldReservation, context: Context, house, reservation):
    _reservation = attr.evolve(reservation, status=ReservationStatuses.NEW)
    context.house = house
    context.source = _reservation

    result = service.check_reservation(context)
    assert is_successful(result), result.failure()
    assert result.unwrap().source == _reservation


def test_check_reservation_ok(service: AcceptHoldReservation, context: Context, house, reservation):
    context.house = house
    context.source = reservation

    result = service.check_reservation(context)
    assert is_successful(result), result.failure()
    assert result.unwrap().source == reservation


def test_accept_reservation_accepted(service: AcceptHoldReservation, context: Context, house, reservation):
    _reservation = attr.evolve(reservation, status=ReservationStatuses.NEW)
    service._reservations_repo = Mock(save=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.source = _reservation

    result = service.accept_reservation(context)
    assert is_successful(result)
    assert result.unwrap().reservation == _reservation


def test_accept_reservation_error(service: AcceptHoldReservation, context: Context, house, reservation):
    service._reservations_repo = Mock(save=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.source = reservation

    result = service.accept_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_accept_reservation_fail(service: AcceptHoldReservation, context: Context, house, reservation):
    service._reservations_repo = Mock(save=Mock(return_value=(Nothing, False)))
    context.house = house
    context.source = reservation

    result = service.accept_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert result.failure().error.startswith('Error save accepted Reservation ID=')


def test_accept_reservation_ok(service: AcceptHoldReservation, context: Context, house, reservation):
    _reservation = attr.evolve(reservation, status=ReservationStatuses.NEW)
    service._reservations_repo = Mock(save=Mock(return_value=(Some(_reservation), True)))
    context.house = house
    context.source = reservation

    result = service.accept_reservation(context)
    assert is_successful(result)
    assert result.unwrap().reservation == _reservation


def test_confirm_quatation_no_quatation_id(service: AcceptHoldReservation, context: Context, house, reservation):
    context.house = house
    context.reservation = attr.evolve(reservation, quotation_id=None)
    context.api = Mock(confirm_quotation=Mock(side_effect=RuntimeError('ERR')))

    result = service.confirm_quotation(context)
    assert is_successful(result)

    context.api.confirm_quotation.assert_not_called()


def test_confirm_quatation_error(service: AcceptHoldReservation, context: Context, house, reservation):
    context.house = house
    context.reservation = attr.evolve(reservation, quotation_id=123)
    context.api = Mock(confirm_quotation=Mock(side_effect=RuntimeError('ERR')))

    result = service.confirm_quotation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_confirm_quatation_ok(service: AcceptHoldReservation, context: Context, house, reservation):
    context.house = house
    context.reservation = attr.evolve(reservation, quotation_id=123)
    context.api = Mock(confirm_quotation=Mock(return_value=None))

    result = service.confirm_quotation(context)
    assert is_successful(result)

    context.api.confirm_quotation.assert_called_once_with(123)


def test_success(service: AcceptHoldReservation, house, reservation, user):
    _reservation = attr.evolve(reservation, status=ReservationStatuses.NEW)
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))
    service._reservations_repo = Mock(
        get=Mock(return_value=Some(reservation)), save=Mock(return_value=(Some(_reservation), True))
    )
    service.get_rpc_api = Mock(return_value=Mock(confirm_quotation=Mock(return_value=None)))

    result = service.execute(house.id, reservation.id, user)
    assert is_successful(result)
    assert result.unwrap()


def test_success_for_accepted(service: AcceptHoldReservation, house, reservation, user):
    _reservation = attr.evolve(reservation, status=ReservationStatuses.NEW)
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))
    service._reservations_repo = Mock(get=Mock(return_value=Some(_reservation)))
    service.get_rpc_api = Mock(return_value=Mock(confirm_quotation=Mock(return_value=None)))

    result = service.execute(house.id, reservation.id, user)
    assert is_successful(result)
    assert result.unwrap()
