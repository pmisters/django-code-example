import datetime
from decimal import Decimal
from unittest.mock import Mock

import attr
import pytest
from django.utils import timezone
from returns.maybe import Nothing, Some
from returns.pipeline import is_successful

from board.entities import Reservation, ReservationDay, ReservationRoom
from board.usecases._move_reservation import Context, MoveReservation  # noqa
from board.value_objects import CachedReservation, ReservationErrors
from effective_tours.constants import ReservationSources, ReservationStatuses


@pytest.fixture()
def service() -> MoveReservation:
    return MoveReservation()


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
        is_verified=True,
        guest_name="John",
        guest_surname="Smith",
        guest_phone="+1-222-3344",
        price=Decimal(1120),
        netto_price=Decimal(1120),
        rooms=[
            ReservationRoom(
                id=211,
                reservation_id=111,
                channel_id="",
                channel_rate_id="",
                checkin=checkin,
                checkout=checkout,
                rate_plan_id=rate_plan.id,
                adults=2,
                children=1,
                price=Decimal(1120),
                netto_price=Decimal(1120),
                day_prices=[
                    ReservationDay(
                        id=311,
                        reservation_room_id=211,
                        day=checkin,
                        roomtype_id=room_type.id,
                        price_original=Decimal(1120),
                        price_accepted=Decimal(1120),
                        currency=house.currency.code,
                    ),
                    ReservationDay(
                        id=312,
                        reservation_room_id=211,
                        day=checkin + datetime.timedelta(days=1),
                        roomtype_id=room_type.id,
                        price_original=Decimal(1120),
                        price_accepted=Decimal(1120),
                        currency=house.currency.code,
                    ),
                    ReservationDay(
                        id=313,
                        reservation_room_id=211,
                        day=checkin + datetime.timedelta(days=2),
                        roomtype_id=room_type.id,
                        price_original=Decimal(1120),
                        price_accepted=Decimal(1120),
                        currency=house.currency.code,
                    ),
                ],
            )
        ],
    )


@pytest.fixture(scope="module")
def cache_reservation(reservation, room_type):
    return CachedReservation(
        pk="111-211-1",
        reservation_id=reservation.id,
        grid="roomtype",
        grid_id=room_type.id,
        checkin=datetime.datetime.combine(datetime.date.today() + datetime.timedelta(days=1), datetime.time(14)),
        checkout=datetime.datetime.combine(datetime.date.today() + datetime.timedelta(days=2), datetime.time(11)),
    )


@pytest.fixture()
def context(house, room, reservation, user):
    return Context(
        pk=f"{reservation.id}-211-1", reservation_id=reservation.id, house_id=house.id, room_id=room.id, user=user
    )


def test_missed_house_id(service: MoveReservation, context: Context):
    context.house_id = None

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_error(service: MoveReservation, context: Context):
    service._houses_repo = Mock(get=Mock(side_effect=RuntimeError("ERR")))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_house_fail(service: MoveReservation, context: Context):
    service._houses_repo = Mock(get=Mock(return_value=Nothing))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_ok(service: MoveReservation, context: Context, house):
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))

    result = service.select_house(context)
    assert is_successful(result), result.failure()
    assert result.unwrap().house == house


def test_missed_reservation_part_id(service: MoveReservation, context: Context, house):
    context.house = house
    context.pk = None

    result = service.select_reservation_from_cache(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_from_cache_error(service: MoveReservation, context: Context, house):
    service._cache_repo = Mock(get=Mock(side_effect=RuntimeError("ERR")))
    context.house = house

    result = service.select_reservation_from_cache(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_reservation_from_cache_fail(service: MoveReservation, context: Context, house):
    service._cache_repo = Mock(get=Mock(return_value=Nothing))
    context.house = house

    result = service.select_reservation_from_cache(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_from_cache_ok(service: MoveReservation, context: Context, house, cache_reservation):
    service._cache_repo = Mock(get=Mock(return_value=Some(cache_reservation)))
    context.house = house

    result = service.select_reservation_from_cache(context)
    assert is_successful(result), result.failure()
    assert result.unwrap().start_date == datetime.date.today() + datetime.timedelta(days=1)
    assert result.unwrap().end_date == datetime.date.today() + datetime.timedelta(days=1)


def test_missed_reservation_id(service: MoveReservation, context: Context, house):
    context.house = house
    context.reservation_id = None

    result = service.select_reservation_from_db(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_from_db_error(service: MoveReservation, context: Context, house):
    service._reservations_repo = Mock(get=Mock(side_effect=RuntimeError("ERR")))
    context.house = house

    result = service.select_reservation_from_db(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_reservation_from_db_fail(service: MoveReservation, context: Context, house):
    service._reservations_repo = Mock(get=Mock(return_value=Nothing))
    context.house = house

    result = service.select_reservation_from_db(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_from_db_ok(service: MoveReservation, context: Context, house, reservation):
    service._reservations_repo = Mock(get=Mock(return_value=Some(reservation)))
    context.house = house

    result = service.select_reservation_from_db(context)
    assert is_successful(result)
    assert result.unwrap().reservation == reservation


def test_select_reservation_from_db_canceled(service: MoveReservation, context: Context, house, reservation):
    canceled_reservation = attr.evolve(reservation, status=ReservationStatuses.CANCEL)
    service._reservations_repo = Mock(get=Mock(return_value=Some(canceled_reservation)))
    context.house = house

    result = service.select_reservation_from_db(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_room_type_error(service: MoveReservation, context: Context, house):
    service._roomtypes_repo = Mock(get=Mock(side_effect=RuntimeError("ERR")))
    context.house = house
    context.roomtype_id = 100

    result = service.select_room_type(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_room_type_fail(service: MoveReservation, context: Context, house):
    service._roomtypes_repo = Mock(get=Mock(return_value=Nothing))
    context.house = house
    context.roomtype_id = 500

    result = service.select_room_type(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_roomtype


def test_select_room_type_ok(service: MoveReservation, context: Context, house, room_type):
    service._roomtypes_repo = Mock(get=Mock(return_value=Some(room_type)))
    context.house = house
    context.roomtype_id = room_type.id

    result = service.select_room_type(context)
    assert is_successful(result), result.failure()
    assert result.unwrap().room_type == room_type


def test_select_room_error(service: MoveReservation, context: Context, house):
    service._rooms_repo = Mock(get=Mock(side_effect=RuntimeError("ERR")))
    context.house = house
    context.roomtype_id = None
    context.room_id = 800

    result = service.select_room(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_room_fail(service: MoveReservation, context: Context, house):
    service._rooms_repo = Mock(get=Mock(return_value=Nothing))
    context.house = house
    context.roomtype_id = None
    context.room_id = 800

    result = service.select_room(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_room


def test_select_room_ok(service: MoveReservation, context: Context, house, room):
    service._rooms_repo = Mock(get=Mock(return_value=Some(room)))
    context.house = house
    context.roomtype_id = None
    context.room_id = room.id

    result = service.select_room(context)
    assert is_successful(result), result.failure()
    assert result.unwrap().room == room


def test_update_reservation_with_room_type(service: MoveReservation, context: Context, house, reservation, room_type):
    context.house = house
    context.reservation = reservation
    context.room_type = attr.evolve(room_type, id=555)
    context.room = None
    context.start_date = datetime.date.today() + datetime.timedelta(days=1)
    context.end_date = datetime.date.today() + datetime.timedelta(days=1)

    result = service.update_reservation(context)
    assert is_successful(result)

    _reservation = result.unwrap().reservation
    assert _reservation.rooms[0].day_prices[0].roomtype_id == room_type.id
    assert _reservation.rooms[0].day_prices[0].room_id is None
    assert _reservation.rooms[0].day_prices[1].roomtype_id == 555
    assert _reservation.rooms[0].day_prices[1].room_id is None
    assert _reservation.rooms[0].day_prices[2].roomtype_id == room_type.id
    assert _reservation.rooms[0].day_prices[2].room_id is None


def test_update_reservation_with_room(
    service: MoveReservation, context: Context, house, reservation, room_type, room
):
    _room = attr.evolve(room, id=555)
    context.house = house
    context.reservation = reservation
    context.room = _room
    context.room_type = None
    context.start_date = datetime.date.today() + datetime.timedelta(days=1)
    context.end_date = datetime.date.today() + datetime.timedelta(days=1)

    result = service.update_reservation(context)
    assert is_successful(result)

    _reservation = result.unwrap().reservation
    assert _reservation.rooms[0].day_prices[0].roomtype_id == room_type.id
    assert _reservation.rooms[0].day_prices[0].room_id is None
    assert _reservation.rooms[0].day_prices[1].roomtype_id == _room.roomtype_id
    assert _reservation.rooms[0].day_prices[1].room_id == _room.id
    assert _reservation.rooms[0].day_prices[2].roomtype_id == room_type.id
    assert _reservation.rooms[0].day_prices[2].room_id is None


def test_save_error(service: MoveReservation, context: Context, house, reservation):
    service._reservations_repo = Mock(save=Mock(side_effect=RuntimeError("ERR")))
    context.house = house
    context.reservation = reservation

    result = service.save(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == "ERR"


def test_save_fail(service: MoveReservation, context: Context, house, reservation):
    service._reservations_repo = Mock(save=Mock(return_value=(Nothing, False)))
    context.house = house
    context.reservation = reservation

    result = service.save(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert result.failure().error.startswith("Error save Reservation ID=")


def test_save_ok(service: MoveReservation, context: Context, house, reservation):
    _reservation = attr.evolve(reservation, promo="X")
    service._reservations_repo = Mock(save=Mock(return_value=(Some(_reservation), True)))
    context.house = house
    context.reservation = reservation

    result = service.save(context)
    assert is_successful(result), result.failure()
    assert result.unwrap().reservation == _reservation


def test_success(service: MoveReservation, context: Context, house, cache_reservation, reservation, user, room):
    _reservation = attr.evolve(reservation, promo="X")
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))
    service._cache_repo = Mock(get=Mock(return_value=Some(cache_reservation)))
    service._reservations_repo = Mock(
        get=Mock(return_value=Some(reservation)), save=Mock(return_value=(Some(_reservation), True))
    )
    service._rooms_repo = Mock(get=Mock(return_value=Some(room)))

    result = service.execute("111-211-1", reservation.id, house.id, room_id=500, user=user)
    assert is_successful(result), result.failure()
