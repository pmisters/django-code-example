import datetime
from decimal import Decimal
from unittest.mock import Mock

import attr
import pytest
from django.utils import timezone
from returns.maybe import Nothing, Some
from returns.pipeline import is_successful

from board.entities import Reservation, ReservationDay, ReservationRoom
from board.usecases._select_reservation import Context, SelectReservation  # noqa
from board.value_objects import ReservationDetailsContext, ReservationErrors
from effective_tours.constants import ReservationSources, ReservationStatuses


@pytest.fixture()
def service() -> SelectReservation:
    return SelectReservation()


@pytest.fixture(scope='module')
def reservation(house, rate_plan, room_type):
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
        status=ReservationStatuses.NEW,
        is_verified=True,
        guest_name='John',
        guest_surname='Smith',
        guest_phone='+1-222-3344',
        guest_contact_id=123,
        guest_contact_ids=[123],
        price=Decimal(1120),
        netto_price=Decimal(1120),
        quotation_id=321,
        rooms=[
            ReservationRoom(
                id=211,
                reservation_id=111,
                channel_id='',
                channel_rate_id='',
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


@pytest.fixture()
def context(house, reservation, user) -> Context:
    return Context(house_id=house.id, pk=reservation.id, user=user)


def test_missed_house_id(service: SelectReservation, context: Context):
    context.house_id = None

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_error(service: SelectReservation, context: Context):
    service._houses_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_house_fail(service: SelectReservation, context: Context):
    service._houses_repo = Mock(get=Mock(return_value=Nothing))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_ok(service: SelectReservation, context: Context, house):
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))

    result = service.select_house(context)
    assert is_successful(result), result.failure()
    assert result.unwrap().house == house


def test_missed_reservation_id(service: SelectReservation, context: Context, house):
    context.house = house
    context.pk = None

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_error(service: SelectReservation, context: Context, house):
    service._reservations_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_reservation_fail(service: SelectReservation, context: Context, house):
    service._reservations_repo = Mock(get=Mock(return_value=Nothing))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_ok(service: SelectReservation, context: Context, house, reservation):
    service._reservations_repo = Mock(get=Mock(return_value=Some(reservation)))
    context.house = house

    result = service.select_reservation(context)
    assert is_successful(result)
    assert result.unwrap().reservation == reservation


def test_check_reservation_wrong_house(service: SelectReservation, context: Context, house, reservation):
    context.house = house
    context.reservation = attr.evolve(reservation, house_id=999)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_check_reservation_room_close(service: SelectReservation, context: Context, house, reservation):
    context.house = house
    context.reservation = attr.evolve(reservation, status=ReservationStatuses.CLOSE)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_check_reservation_ok(service: SelectReservation, context: Context, house, reservation):
    context.house = house
    context.reservation = reservation

    result = service.check_reservation(context)
    assert is_successful(result)


def test_populate_with_rate_plans_error(service: SelectReservation, context: Context, house, reservation):
    service._prices_repo = Mock(select_plans=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.reservation = reservation

    result = service.populate_with_rate_plans(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_populate_with_rate_plans_fail(service: SelectReservation, context: Context, house, reservation):
    service._prices_repo = Mock(select_plans=Mock(return_value=[]))
    context.house = house
    context.reservation = reservation

    result = service.populate_with_rate_plans(context)
    assert is_successful(result)
    assert result.unwrap().reservation.rooms[0].rate_plan is None


def test_populate_with_rate_plans_ok(service: SelectReservation, context: Context, house, rate_plan, reservation):
    service._prices_repo = Mock(select_plans=Mock(return_value=[rate_plan]))
    context.house = house
    context.reservation = reservation

    result = service.populate_with_rate_plans(context)
    assert is_successful(result)
    assert result.unwrap().reservation.rooms[0].rate_plan == rate_plan


def test_populate_with_room_types_error(service: SelectReservation, context: Context, house, reservation):
    service._roomtypes_repo = Mock(select=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.reservation = reservation

    result = service.populate_with_room_types(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_populate_with_room_types_fail(service: SelectReservation, context: Context, house, reservation):
    service._roomtypes_repo = Mock(select=Mock(return_value=[]))
    context.house = house
    context.reservation = reservation

    result = service.populate_with_room_types(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert result.failure().error.startswith('Empty list of Room Types in House')


def test_populate_with_room_types_ok(service: SelectReservation, context: Context, house, reservation, room_type):
    service._roomtypes_repo = Mock(select=Mock(return_value=[room_type]))
    context.house = house
    context.reservation = reservation

    result = service.populate_with_room_types(context)
    assert is_successful(result)
    for price in result.unwrap().reservation.rooms[0].day_prices:
        assert price.room_type == room_type


def test_populate_with_rooms_no_assigned(service: SelectReservation, context: Context, house, reservation):
    service._rooms_repo = Mock(select=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.reservation = reservation

    result = service.populate_with_rooms(context)
    assert is_successful(result)
    for price in result.unwrap().reservation.rooms[0].day_prices:
        assert price.room is None


def test_populate_with_rooms_error(service: SelectReservation, context: Context, house, reservation, room):
    service._rooms_repo = Mock(select=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.reservation = attr.evolve(reservation)
    context.reservation.rooms[0].day_prices[0].room_id = room.id

    result = service.populate_with_rooms(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_populate_with_rooms_fail(service: SelectReservation, context: Context, house, reservation, room):
    service._rooms_repo = Mock(select=Mock(return_value=[]))
    context.house = house
    context.reservation = attr.evolve(reservation)
    context.reservation.rooms[0].day_prices[0].room_id = room.id

    result = service.populate_with_rooms(context)
    assert is_successful(result)
    for price in result.unwrap().reservation.rooms[0].day_prices:
        assert price.room is None


def test_populate_with_rooms_ok(service: SelectReservation, context: Context, house, reservation, room):
    service._rooms_repo = Mock(select=Mock(return_value=[room]))
    context.house = house
    context.reservation = attr.evolve(reservation)
    context.reservation.rooms[0].day_prices[0].room_id = room.id

    result = service.populate_with_rooms(context)
    assert is_successful(result)

    ctx = result.unwrap()
    assert ctx.reservation.rooms[0].day_prices[0].room == room
    assert ctx.reservation.rooms[0].day_prices[1].room is None
    assert ctx.reservation.rooms[0].day_prices[2].room is None


def test_select_payed_amount_not_quotation_id(service: SelectReservation, context: Context, house, reservation):
    context.house = house
    context.reservation = attr.evolve(reservation, quotation_id=None)

    result = service.select_payed_amount(context)
    assert is_successful(result)
    assert result.unwrap().payed_amount == Decimal(0)


def test_select_payed_amount_error(service: SelectReservation, context: Context, house, reservation):
    context.house = house
    context.reservation = reservation
    context.api = Mock(select_invoices_for_order=Mock(side_effect=RuntimeError('ERR')))

    result = service.select_payed_amount(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_payed_amount_empty(service: SelectReservation, context: Context, house, reservation):
    context.house = house
    context.reservation = reservation
    context.api = Mock(select_invoices_for_order=Mock(return_value=[]))

    result = service.select_payed_amount(context)
    assert is_successful(result)
    assert result.unwrap().payed_amount == Decimal(0)


def test_select_payed_amount_ok(service: SelectReservation, context: Context, house, reservation):
    context.house = house
    context.reservation = reservation
    context.api = Mock(
        select_invoices_for_order=Mock(
            return_value=[
                Mock(id=987, amount_total=50.0, amount_residual=30.0),
                Mock(id=988, amount_total=50.0, amount_residual=10.0),
            ]
        )
    )

    result = service.select_payed_amount(context)
    assert is_successful(result)
    assert result.unwrap().payed_amount == Decimal(60)

    context.api.select_invoices_for_order.assert_called_once_with(321)


def test_success(service: SelectReservation, house, rate_plan, reservation, user, room_type):
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))
    service._reservations_repo = Mock(get=Mock(return_value=Some(reservation)))
    service._prices_repo = Mock(select_plans=Mock(return_value=[rate_plan]))
    service._roomtypes_repo = Mock(select=Mock(return_value=[room_type]))
    service._rooms_repo = Mock(select=Mock(return_value=[]))
    service.get_rpc_api = Mock(
        return_value=Mock(
            select_invoices_for_order=Mock(
                return_value=[
                    Mock(id=987, amount_total=50.0, amount_residual=30.0),
                    Mock(id=988, amount_total=50.0, amount_residual=10.0),
                ]
            )
        )
    )

    result = service.execute(house.id, reservation.id, user)
    assert is_successful(result)

    ctx = result.unwrap()
    assert isinstance(ctx, ReservationDetailsContext)
    assert ctx.house == house
    assert ctx.reservation == reservation
    assert ctx.payed_amount == Decimal(60)
