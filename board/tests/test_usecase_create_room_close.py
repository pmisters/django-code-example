import datetime
from decimal import Decimal
from unittest.mock import Mock

import attr
import pytest
from django.utils import timezone
from returns.maybe import Nothing, Some
from returns.pipeline import is_successful

from board.entities import Reservation, ReservationDay, ReservationRoom
from board.usecases._create_room_close import Context, CreateRoomClose  # noqa
from board.value_objects import ReservationErrors
from effective_tours.constants import ReservationSources, ReservationStatuses, RoomCloseReasons


@pytest.fixture()
def service() -> CreateRoomClose:
    return CreateRoomClose()


@pytest.fixture()
def context(house, room, user) -> Context:
    return Context(
        house_id=house.id,
        room_id=room.id,
        start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=2),
        reason=RoomCloseReasons.MAINTENANCE,
        user=user,
        notes="Comment",
    )


def test_missed_house_id(service: CreateRoomClose, context: Context):
    context.house_id = None

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_error(service: CreateRoomClose, context: Context):
    service._houses_repo = Mock(get=Mock(side_effect=RuntimeError("ERR")))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_house_fail(service: CreateRoomClose, context: Context):
    service._houses_repo = Mock(get=Mock(return_value=Nothing))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_ok(service: CreateRoomClose, context: Context, house):
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))

    result = service.select_house(context)
    assert is_successful(result)
    assert result.unwrap().house == house


def test_missed_room(service: CreateRoomClose, context: Context, house):
    context.house = house
    context.room_id = None

    result = service.select_room(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_room


def test_select_room_error(service: CreateRoomClose, context: Context, house):
    service._rooms_repo = Mock(get=Mock(side_effect=RuntimeError("ERR")))
    context.house = house

    result = service.select_room(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_room_fail(service: CreateRoomClose, context: Context, house):
    service._rooms_repo = Mock(get=Mock(return_value=Nothing))
    context.house = house

    result = service.select_room(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_room


def test_select_room_ok(service: CreateRoomClose, context: Context, house, room):
    service._rooms_repo = Mock(get=Mock(return_value=Some(room)))
    context.house = house

    result = service.select_room(context)
    assert is_successful(result)
    assert result.unwrap().room == room


def test_check_room_is_free_error(service: CreateRoomClose, context: Context, house, room):
    service._reservations_repo = Mock(is_room_busy=Mock(side_effect=RuntimeError("ERR")))
    context.house = house
    context.room = room

    result = service.check_room_is_free(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_check_room_is_free_fail(service: CreateRoomClose, context: Context, house, room):
    service._reservations_repo = Mock(is_room_busy=Mock(return_value=True))
    context.house = house
    context.room = room

    result = service.check_room_is_free(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.busy_room


def test_check_room_is_free_ok(service: CreateRoomClose, context: Context, house, room):
    service._reservations_repo = Mock(is_room_busy=Mock(return_value=False))
    context.house = house
    context.room = room

    result = service.check_room_is_free(context)
    assert is_successful(result), result.failure()


def test_make_reservation_from_data(service: CreateRoomClose, context: Context, house, room):
    context.house = house
    context.room = room

    result = service.make_reservation_from_date(context)
    assert is_successful(result), result.failure()

    reservation = result.unwrap().reservation
    assert isinstance(reservation, Reservation)
    assert reservation.id is None
    assert reservation.house_id == house.id
    assert reservation.connection_id is None
    assert reservation.source == ReservationSources.MANUAL
    assert reservation.channel is None
    assert reservation.channel_id == ""
    assert reservation.checkin == context.start_date
    assert reservation.checkout == context.end_date
    assert reservation.status == ReservationStatuses.CLOSE
    assert reservation.close_reason == RoomCloseReasons.MAINTENANCE
    assert reservation.room_count == 1
    assert reservation.currency == house.currency.code
    assert reservation.price == Decimal(0)
    assert reservation.tax == Decimal(0)
    assert reservation.fees == Decimal(0)
    assert reservation.netto_price == Decimal(0)

    assert len(reservation.rooms) == 1

    reservation_room = reservation.rooms[0]
    assert isinstance(reservation_room, ReservationRoom)
    assert reservation_room.id is None
    assert reservation_room.channel_id == ""
    assert reservation_room.channel_rate_id == ""
    assert reservation_room.checkin == context.start_date
    assert reservation_room.checkout == context.end_date
    assert reservation_room.rate_plan_id is None
    assert reservation_room.rate_id is None
    assert reservation_room.notes_info == "Comment"

    assert len(reservation_room.day_prices) == 2

    price = reservation_room.day_prices[0]
    assert isinstance(price, ReservationDay)
    assert price.id is None
    assert price.day == context.start_date
    assert price.roomtype_id == room.roomtype_id
    assert price.room_id == room.id
    assert price.price_original == Decimal(0)
    assert price.price_accepted == Decimal(0)
    assert price.tax == Decimal(0)
    assert price.currency == house.currency.code

    price = reservation_room.day_prices[1]
    assert isinstance(price, ReservationDay)
    assert price.id is None
    assert price.day == context.start_date + datetime.timedelta(days=1)
    assert price.roomtype_id == room.roomtype_id
    assert price.room_id == room.id
    assert price.price_original == Decimal(0)
    assert price.price_accepted == Decimal(0)
    assert price.tax == Decimal(0)
    assert price.currency == house.currency.code


def test_save_reservation_error(service: CreateRoomClose, context: Context, house, room):
    service._reservations_repo = Mock(save=Mock(side_effect=RuntimeError("ERR")))
    context.house = house
    context.room = room
    context.reservation = Reservation(
        id=None,
        house_id=house.id,
        connection_id=None,
        source=ReservationSources.MANUAL,
        channel=None,
        channel_id="",
        checkin=context.start_date,
        checkout=context.end_date,
        booked_at=timezone.now(),
        status=ReservationStatuses.CLOSE,
    )

    result = service.save_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_save_reservation_fail(service: CreateRoomClose, context: Context, house, room):
    service._reservations_repo = Mock(save=Mock(return_value=(Nothing, False)))
    context.house = house
    context.room = room
    context.reservation = Reservation(
        id=None,
        house_id=house.id,
        connection_id=None,
        source=ReservationSources.MANUAL,
        channel=None,
        channel_id="",
        checkin=context.start_date,
        checkout=context.end_date,
        booked_at=timezone.now(),
        status=ReservationStatuses.CLOSE,
    )

    result = service.save_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.save
    assert result.failure().error.startswith("Error save Reservation")


def test_save_reservation_ok(service: CreateRoomClose, context: Context, house, room):
    reservation = Reservation(
        id=111,
        house_id=house.id,
        connection_id=None,
        source=ReservationSources.MANUAL,
        channel=None,
        channel_id="",
        checkin=context.start_date,
        checkout=context.end_date,
        booked_at=timezone.now(),
        status=ReservationStatuses.CLOSE,
    )
    service._reservations_repo = Mock(save=Mock(return_value=(Some(reservation), True)))
    context.house = house
    context.room = room
    context.reservation = attr.evolve(reservation, id=None)

    result = service.save_reservation(context)
    assert is_successful(result)
    assert result.unwrap().reservation == reservation


def test_accept_reservation_error(service: CreateRoomClose, context: Context, house, room):
    service._reservations_repo = Mock(accept=Mock(side_effect=RuntimeError("ERR")))
    context.house = house
    context.room = room
    context.reservation = Reservation(
        id=111,
        house_id=house.id,
        connection_id=None,
        source=ReservationSources.MANUAL,
        channel=None,
        channel_id="",
        checkin=context.start_date,
        checkout=context.end_date,
        booked_at=timezone.now(),
        status=ReservationStatuses.CLOSE,
    )

    result = service.accept_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_accept_reservation_fail(service: CreateRoomClose, context: Context, house, room):
    service._reservations_repo = Mock(accept=Mock(return_value=Nothing))
    context.house = house
    context.room = room
    context.reservation = Reservation(
        id=111,
        house_id=house.id,
        connection_id=None,
        source=ReservationSources.MANUAL,
        channel=None,
        channel_id="",
        checkin=context.start_date,
        checkout=context.end_date,
        booked_at=timezone.now(),
        status=ReservationStatuses.CLOSE,
    )

    result = service.accept_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.save
    assert result.failure().error.startswith("Error accept new Reservation")


def test_accept_reservation_ok(service: CreateRoomClose, context: Context, house, room):
    reservation = Reservation(
        id=111,
        house_id=house.id,
        connection_id=None,
        source=ReservationSources.MANUAL,
        channel=None,
        channel_id="",
        checkin=context.start_date,
        checkout=context.end_date,
        booked_at=timezone.now(),
        status=ReservationStatuses.CLOSE,
        is_verified=True,
    )
    service._reservations_repo = Mock(accept=Mock(return_value=Some(reservation)))
    context.house = house
    context.room = room
    context.reservation = attr.evolve(reservation, is_verified=False)

    result = service.accept_reservation(context)
    assert is_successful(result)
    assert result.unwrap().reservation == reservation


def test_success(service: CreateRoomClose, context: Context, house, room):
    reservation = Reservation(
        id=111,
        house_id=house.id,
        connection_id=None,
        source=ReservationSources.MANUAL,
        channel=None,
        channel_id="",
        checkin=context.start_date,
        checkout=context.end_date,
        booked_at=timezone.now(),
        status=ReservationStatuses.CLOSE,
        is_verified=True,
    )
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))
    service._rooms_repo = Mock(get=Mock(return_value=Some(room)))
    service._reservations_repo = Mock(
        save=Mock(return_value=(Some(attr.evolve(reservation, is_verified=False)), True)),
        accept=Mock(return_value=Some(reservation)),
        is_room_busy=Mock(return_value=False),
    )

    result = service.execute(
        house.id, room.id, context.start_date, context.end_date, RoomCloseReasons.MAINTENANCE, context.user
    )
    assert is_successful(result), result.failure()
    assert result.unwrap() == attr.evolve(reservation, is_verified=True)
