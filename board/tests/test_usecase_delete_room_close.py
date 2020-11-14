import datetime
from unittest.mock import Mock

import attr
import pytest
from django.utils import timezone
from returns.maybe import Nothing, Some
from returns.pipeline import is_successful

from board.entities import Reservation, ReservationDay, ReservationRoom
from board.usecases._delete_room_close import Context, DeleteRoomClose  # noqa
from board.value_objects import ReservationErrors
from effective_tours.constants import ReservationSources, ReservationStatuses


@pytest.fixture()
def service() -> DeleteRoomClose:
    return DeleteRoomClose()


@pytest.fixture()
def reservation(house, room):
    checkin = datetime.date.today()
    checkout = checkin + datetime.timedelta(days=2)
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
        status=ReservationStatuses.CLOSE,
        is_verified=True,
        rooms=[
            ReservationRoom(
                id=222,
                reservation_id=111,
                channel_id="",
                channel_rate_id="",
                checkin=checkin,
                checkout=checkout,
                notes_info="XXX",
                day_prices=[
                    ReservationDay(
                        id=1, reservation_room_id=222, day=checkin, roomtype_id=room.roomtype_id, room_id=room.id
                    ),
                    ReservationDay(
                        id=2,
                        reservation_room_id=222,
                        day=checkin + datetime.timedelta(days=1),
                        roomtype_id=room.roomtype_id,
                        room_id=room.id,
                    ),
                ],
            )
        ],
    )


@pytest.fixture()
def context(house, user) -> Context:
    return Context(pk=111, house_id=house.id, user=user)


def test_missed_house_id(service: DeleteRoomClose, context: Context):
    context.house_id = None

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_error(service: DeleteRoomClose, context: Context):
    service._houses_repo = Mock(get=Mock(side_effect=RuntimeError("ERR")))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_house_fail(service: DeleteRoomClose, context: Context):
    service._houses_repo = Mock(get=Mock(return_value=Nothing))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_ok(service: DeleteRoomClose, context: Context, house):
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))

    result = service.select_house(context)
    assert is_successful(result)
    assert result.unwrap().house == house


def test_select_reservation_missed_pk(service: DeleteRoomClose, context: Context, house):
    context.house = house
    context.pk = None

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_error(service: DeleteRoomClose, context: Context, house):
    service._reservations_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_reservation_fail(service: DeleteRoomClose, context: Context, house):
    service._reservations_repo = Mock(get=Mock(return_value=Nothing))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_ok(service: DeleteRoomClose, context: Context, house, reservation):
    service._reservations_repo = Mock(get=Mock(return_value=Some(reservation)))
    context.house = house

    result = service.select_reservation(context)
    assert is_successful(result)
    assert result.unwrap().reservation == reservation


def test_check_reservation_not_close_room(service: DeleteRoomClose, context: Context, house, reservation):
    context.house = house
    context.reservation = attr.evolve(reservation, status=ReservationStatuses.NEW)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_check_reservation_ok(service: DeleteRoomClose, context: Context, house, reservation):
    context.house = house
    context.reservation = reservation

    result = service.check_reservation(context)
    assert is_successful(result)


def test_make_reservation_from_data(service: DeleteRoomClose, context: Context, house, reservation):
    context.house = house
    context.reservation = reservation

    result = service.make_reservation_from_data(context)
    assert is_successful(result), result.failure()

    assert result.unwrap().reservation == attr.evolve(reservation, status=ReservationStatuses.CANCEL)


def test_save_reservation_error(service: DeleteRoomClose, context: Context, house, reservation):
    service._reservations_repo = Mock(save=Mock(side_effect=RuntimeError("ERR")))
    context.house = house
    context.reservation = reservation

    result = service.save_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_save_reservation_fail(service: DeleteRoomClose, context: Context, house, reservation):
    service._reservations_repo = Mock(save=Mock(return_value=(Nothing, False)))
    context.house = house
    context.reservation = reservation

    result = service.save_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.save
    assert result.failure().error.startswith("Error save Reservation")


def test_save_reservation_ok(service: DeleteRoomClose, context: Context, house, reservation):
    _reservation = attr.evolve(reservation, status=ReservationStatuses.CANCEL)
    service._reservations_repo = Mock(save=Mock(return_value=(Some(_reservation), True)))
    context.house = house
    context.reservation = reservation

    result = service.save_reservation(context)
    assert is_successful(result)
    assert result.unwrap().reservation == _reservation


def test_success(service: DeleteRoomClose, house, reservation, user):
    _reservation = attr.evolve(reservation, status=ReservationStatuses.CANCEL)
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))
    service._reservations_repo = Mock(
        get=Mock(return_value=Some(reservation)), save=Mock(return_value=(Some(_reservation), True))
    )

    result = service.execute('111-222-1', house.id, user)
    assert is_successful(result), result.failure()
    assert result.unwrap() == _reservation
