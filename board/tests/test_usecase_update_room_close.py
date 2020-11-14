import datetime
from unittest.mock import Mock

import attr
import pytest
from django.utils import timezone
from returns.maybe import Nothing, Some
from returns.pipeline import is_successful

from board.entities import Reservation, ReservationDay, ReservationRoom
from board.usecases._update_room_close import Context, UpdateRoomClose  # noqa
from board.value_objects import ReservationErrors, ReservationUpdateContext
from effective_tours.constants import ReservationSources, ReservationStatuses, RoomCloseReasons


@pytest.fixture()
def service() -> UpdateRoomClose:
    return UpdateRoomClose()


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
def context(house, room, user) -> Context:
    return Context(
        pk=111,
        house_id=house.id,
        room_id=room.id,
        start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=2),
        reason=RoomCloseReasons.MAINTENANCE,
        user=user,
        notes="Comment",
    )


def test_missed_house_id(service: UpdateRoomClose, context: Context):
    context.house_id = None

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_error(service: UpdateRoomClose, context: Context):
    service._houses_repo = Mock(get=Mock(side_effect=RuntimeError("ERR")))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_house_fail(service: UpdateRoomClose, context: Context):
    service._houses_repo = Mock(get=Mock(return_value=Nothing))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_ok(service: UpdateRoomClose, context: Context, house):
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))

    result = service.select_house(context)
    assert is_successful(result)
    assert result.unwrap().house == house


def test_missed_room(service: UpdateRoomClose, context: Context, house):
    context.house = house
    context.room_id = None

    result = service.select_room(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_room


def test_select_room_error(service: UpdateRoomClose, context: Context, house):
    service._rooms_repo = Mock(get=Mock(side_effect=RuntimeError("ERR")))
    context.house = house

    result = service.select_room(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_room_fail(service: UpdateRoomClose, context: Context, house):
    service._rooms_repo = Mock(get=Mock(return_value=Nothing))
    context.house = house

    result = service.select_room(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_room


def test_select_room_ok(service: UpdateRoomClose, context: Context, house, room):
    service._rooms_repo = Mock(get=Mock(return_value=Some(room)))
    context.house = house

    result = service.select_room(context)
    assert is_successful(result)
    assert result.unwrap().room == room


def test_select_reservation_missed_pk(service: UpdateRoomClose, context: Context, house):
    context.house = house
    context.pk = None

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_error(service: UpdateRoomClose, context: Context, house):
    service._reservations_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_reservation_fail(service: UpdateRoomClose, context: Context, house):
    service._reservations_repo = Mock(get=Mock(return_value=Nothing))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_ok(service: UpdateRoomClose, context: Context, house, reservation):
    service._reservations_repo = Mock(get=Mock(return_value=Some(reservation)))
    context.house = house

    result = service.select_reservation(context)
    assert is_successful(result)
    assert result.unwrap().source == reservation


def test_check_reservation_not_close_room(service: UpdateRoomClose, context: Context, house, reservation):
    context.house = house
    context.source = attr.evolve(reservation, status=ReservationStatuses.NEW)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_check_reservation_ok(service: UpdateRoomClose, context: Context, house, reservation):
    context.house = house
    context.source = reservation

    result = service.check_reservation(context)
    assert is_successful(result)


def test_check_room_is_free_error(service: UpdateRoomClose, context: Context, house, room, reservation):
    service._reservations_repo = Mock(is_room_busy=Mock(side_effect=RuntimeError("ERR")))
    context.house = house
    context.room = room
    context.source = reservation

    result = service.check_room_is_free(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_check_room_is_free_fail(service: UpdateRoomClose, context: Context, house, room, reservation):
    service._reservations_repo = Mock(is_room_busy=Mock(return_value=True))
    context.house = house
    context.room = room
    context.source = reservation

    result = service.check_room_is_free(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.busy_room


def test_check_room_is_free_ok(service: UpdateRoomClose, context: Context, house, room, reservation):
    service._reservations_repo = Mock(is_room_busy=Mock(return_value=False))
    context.house = house
    context.room = room
    context.source = reservation

    result = service.check_room_is_free(context)
    assert is_successful(result), result.failure()


def test_make_reservation_from_data(service: UpdateRoomClose, context: Context, house, room, reservation):
    context.house = house
    context.room = room
    context.source = reservation

    result = service.make_reservation_from_data(context)
    assert is_successful(result), result.failure()

    _reservation = result.unwrap().reservation
    assert _reservation.id == reservation.id
    assert _reservation.checkin == context.start_date
    assert _reservation.checkout == context.end_date
    assert _reservation.status == ReservationStatuses.CLOSE
    assert _reservation.close_reason == RoomCloseReasons.MAINTENANCE

    assert len(_reservation.rooms) == 1

    _room = _reservation.rooms[0]
    assert _room.id == reservation.rooms[0].id
    assert _room.checkin == context.start_date
    assert _room.checkout == context.end_date
    assert _room.notes_info == "Comment"

    assert len(_room.day_prices) == 2

    price = _room.day_prices[0]
    assert price.id == reservation.rooms[0].day_prices[0].id
    assert price.day == context.start_date
    assert price.roomtype_id == room.roomtype_id
    assert price.room_id == room.id

    price = _room.day_prices[1]
    assert price.id == reservation.rooms[0].day_prices[1].id
    assert price.day == context.start_date + datetime.timedelta(days=1)
    assert price.roomtype_id == room.roomtype_id
    assert price.room_id == room.id


def test_make_reservation_from_data_change_period(
    service: UpdateRoomClose, context: Context, house, room, reservation
):
    context.house = house
    context.room = room
    context.source = reservation
    context.start_date = reservation.checkin + datetime.timedelta(days=10)
    context.end_date = reservation.checkout + datetime.timedelta(days=10)

    result = service.make_reservation_from_data(context)
    assert is_successful(result), result.failure()

    _reservation = result.unwrap().reservation
    assert _reservation.id == reservation.id
    assert _reservation.checkin == context.start_date
    assert _reservation.checkout == context.end_date
    assert _reservation.status == ReservationStatuses.CLOSE
    assert _reservation.close_reason == RoomCloseReasons.MAINTENANCE

    assert len(_reservation.rooms) == 1

    _room = _reservation.rooms[0]
    assert _room.id == reservation.rooms[0].id
    assert _room.checkin == context.start_date
    assert _room.checkout == context.end_date
    assert _room.notes_info == "Comment"

    assert len(_room.day_prices) == 2

    price = _room.day_prices[0]
    assert price.id is None
    assert price.day == context.start_date
    assert price.roomtype_id == room.roomtype_id
    assert price.room_id == room.id

    price = _room.day_prices[1]
    assert price.id is None
    assert price.day == context.start_date + datetime.timedelta(days=1)
    assert price.roomtype_id == room.roomtype_id
    assert price.room_id == room.id


def test_save_reservation_error(service: UpdateRoomClose, context: Context, house, room, reservation):
    service._reservations_repo = Mock(save=Mock(side_effect=RuntimeError("ERR")))
    context.house = house
    context.room = room
    context.reservation = reservation

    result = service.save_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_save_reservation_fail(service: UpdateRoomClose, context: Context, house, room, reservation):
    service._reservations_repo = Mock(save=Mock(return_value=(Nothing, False)))
    context.house = house
    context.room = room
    context.reservation = reservation

    result = service.save_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.save
    assert result.failure().error.startswith("Error save Reservation")


def test_save_reservation_ok(service: UpdateRoomClose, context: Context, house, room, reservation):
    _reservation = attr.evolve(reservation, close_reason=RoomCloseReasons.TMP_CLOSE)
    service._reservations_repo = Mock(save=Mock(return_value=(Some(_reservation), True)))
    context.house = house
    context.room = room
    context.reservation = reservation

    result = service.save_reservation(context)
    assert is_successful(result)
    assert result.unwrap().reservation == _reservation


def test_accept_reservation_error(service: UpdateRoomClose, context: Context, house, room, reservation):
    service._reservations_repo = Mock(accept=Mock(side_effect=RuntimeError("ERR")))
    context.house = house
    context.room = room
    context.reservation = reservation

    result = service.accept_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_accept_reservation_fail(service: UpdateRoomClose, context: Context, house, room, reservation):
    service._reservations_repo = Mock(accept=Mock(return_value=Nothing))
    context.house = house
    context.room = room
    context.reservation = reservation

    result = service.accept_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.save
    assert result.failure().error.startswith("Error accept Reservation ID=")


def test_accept_reservation_ok(service: UpdateRoomClose, context: Context, house, room, reservation):
    reservation = attr.evolve(reservation, is_verified=True)
    service._reservations_repo = Mock(accept=Mock(return_value=Some(reservation)))
    context.house = house
    context.room = room
    context.reservation = attr.evolve(reservation, is_verified=False)

    result = service.accept_reservation(context)
    assert is_successful(result)
    assert result.unwrap().reservation == reservation


def test_success(service: UpdateRoomClose, context: Context, house, room, reservation):
    _reservation = attr.evolve(reservation, is_verified=True)
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))
    service._rooms_repo = Mock(get=Mock(return_value=Some(room)))
    service._reservations_repo = Mock(
        accept=Mock(return_value=Some(_reservation)),
        get=Mock(return_value=Some(reservation)),
        is_room_busy=Mock(return_value=False),
        save=Mock(return_value=(Some(attr.evolve(reservation, is_verified=False)), True)),
    )

    result = service.execute(
        '111-222-1',
        house.id,
        room.id,
        context.start_date,
        context.end_date,
        RoomCloseReasons.MAINTENANCE,
        context.user,
    )
    assert is_successful(result), result.failure()

    ctx = result.unwrap()
    assert isinstance(ctx, ReservationUpdateContext)
    assert ctx.reservation == _reservation
    assert ctx.start_date == datetime.date.today()
    assert ctx.end_date == datetime.date.today() + datetime.timedelta(days=2)
