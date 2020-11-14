import datetime
from decimal import Decimal

import attr
import pytest
from django.utils import timezone

from board.entities import Reservation, ReservationRoom
from effective_tours.constants import ReservationSources, ReservationStatuses


@pytest.fixture()
def reservation(house, room_type, rate_plan):
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
        guest_name='John',
        guest_surname='Smith',
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
                netto_price=Decimal(1120)
            )
        ]
    )


def test_reservation_allow_delete_for_manual(reservation):
    _reservation = attr.evolve(reservation, source=ReservationSources.MANUAL)
    assert _reservation.allow_delete()


def test_reservation_allow_delete_for_ota(reservation):
    _reservation = attr.evolve(reservation, source=ReservationSources.BOOKING)
    assert not _reservation.allow_delete()


def test_reservation_allow_update_prices_for_new(reservation):
    _reservation = attr.evolve(reservation, status=ReservationStatuses.NEW)
    assert _reservation.allow_update_prices()


def test_reservation_allow_update_prices_for_modify(reservation):
    _reservation = attr.evolve(reservation, status=ReservationStatuses.MODIFY)
    assert _reservation.allow_update_prices()


def test_reservation_allow_update_prices_for_cancel(reservation):
    _reservation = attr.evolve(reservation, status=ReservationStatuses.CANCEL)
    assert not _reservation.allow_update_prices()


def test_reservation_allow_update_prices_for_close(reservation):
    _reservation = attr.evolve(reservation, status=ReservationStatuses.CLOSE)
    assert not _reservation.allow_update_prices()


def test_reservation_get_guest_name(reservation):
    assert reservation.get_guest_name() == 'John Smith'


def test_reservation_get_id_manual(reservation):
    assert reservation.get_id() == 'ET111'


def test_reservation_get_id_ota(reservation):
    _reservation = attr.evolve(reservation, channel_id='12341234', source=ReservationSources.BOOKING)
    assert _reservation.get_id() == '12341234'


def test_reservation_get_id_for_log(reservation):
    _reservation = attr.evolve(reservation, checkin=datetime.date(2020, 11, 15), checkout=datetime.date(2020, 11, 20))
    assert _reservation.get_id_for_log() == 'ET111 15/11/2020..20/11/2020'


def test_reservation_get_nights(reservation):
    assert reservation.get_nights() == 3


def test_reservation_get_total_adults(reservation):
    assert reservation.get_total_adults() == 2


def test_reservation_get_total_adults_no_rooms(reservation):
    _reservation = attr.evolve(reservation, rooms=[])
    assert _reservation.get_total_adults() == 0


def test_reservation_get_total_children(reservation):
    assert reservation.get_total_children() == 1


def test_reservation_get_total_children_no_rooms(reservation):
    _reservation = attr.evolve(reservation, rooms=[])
    assert _reservation.get_total_children() == 0


def test_reservation_is_ota_manual(reservation):
    assert not reservation.is_ota()


def test_reservation_is_ota_booking(reservation):
    _reservation = attr.evolve(reservation, source=ReservationSources.BOOKING)
    assert _reservation.is_ota()


def test_reservation_get_opportunity_name(reservation):
    _reservation = attr.evolve(reservation, checkin=datetime.date(2020, 11, 15), checkout=datetime.date(2020, 11, 20))
    assert _reservation.get_opportunity_name() == '15.Nov-20.Nov, John Smith'
