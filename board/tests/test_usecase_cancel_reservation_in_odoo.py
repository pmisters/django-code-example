import datetime
from decimal import Decimal
from unittest.mock import Mock

import attr
import pytest
from django.utils import timezone
from returns.maybe import Nothing, Some
from returns.pipeline import is_successful

from board.entities import Reservation
from board.usecases._cancel_reservation_in_odoo import CancelReservationInOdoo, Context  # noqa
from board.value_objects import ReservationErrors
from effective_tours.constants import ReservationSources, ReservationStatuses
from odoo.value_objects import CrmLostReasons


@pytest.fixture()
def service() -> CancelReservationInOdoo:
    return CancelReservationInOdoo()


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
        status=ReservationStatuses.CANCEL,
        price=Decimal(3360),
        netto_price=Decimal(3360),
        guest_name='John',
        guest_surname='Smith',
        opportunity_id=321,
        quotation_id=123,
    )


@pytest.fixture()
def context(house, reservation, user) -> Context:
    return Context(house_id=house.id, pk=reservation.id, user_id=user.id)


def test_missed_house_id(service: CancelReservationInOdoo, context: Context):
    context.house_id = None

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_error(service: CancelReservationInOdoo, context: Context):
    service._houses_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_house_fail(service: CancelReservationInOdoo, context: Context):
    service._houses_repo = Mock(get=Mock(return_value=Nothing))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_ok(service: CancelReservationInOdoo, context: Context, house):
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))

    result = service.select_house(context)
    assert is_successful(result)
    assert result.unwrap().house == house


def test_select_reservation_missed_pk(service: CancelReservationInOdoo, context: Context, house):
    context.house = house
    context.pk = None

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_error(service: CancelReservationInOdoo, context: Context, house):
    service._reservations_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_reservation_fail(service: CancelReservationInOdoo, context: Context, house):
    service._reservations_repo = Mock(get=Mock(return_value=Nothing))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_ok(service: CancelReservationInOdoo, context: Context, house, reservation):
    service._reservations_repo = Mock(get=Mock(return_value=Some(reservation)))
    context.house = house

    result = service.select_reservation(context)
    assert is_successful(result)
    assert result.unwrap().reservation == reservation


def test_check_reservation_wrong_house(service: CancelReservationInOdoo, context: Context, house, reservation):
    context.house = house
    context.reservation = attr.evolve(reservation, house_id=999)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_check_reservation_room_close(service: CancelReservationInOdoo, context: Context, house, reservation):
    context.house = house
    context.reservation = attr.evolve(reservation, status=ReservationStatuses.CLOSE)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.room_close_reservation


def test_check_reservation_not_cancelled(service: CancelReservationInOdoo, context: Context, house, reservation):
    context.house = house
    context.reservation = attr.evolve(reservation, status=ReservationStatuses.MODIFY)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_user_error(service: CancelReservationInOdoo, context: Context, house):
    service._members_repo = Mock(get_user_by_id=Mock(side_effect=RuntimeError('ERR')))
    context.house = house

    result = service.select_user(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_user
    assert str(result.failure().exc) == 'ERR'


def test_select_user_fail(service: CancelReservationInOdoo, context: Context, house):
    service._members_repo = Mock(get_user_by_id=Mock(return_value=Nothing))
    context.house = house

    result = service.select_user(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_user


def test_select_user_ok(service: CancelReservationInOdoo, context: Context, house, user):
    service._members_repo = Mock(get_user_by_id=Mock(return_value=Some(user)))
    context.house = house

    result = service.select_user(context)
    assert is_successful(result)
    assert result.unwrap().user == user


def test_select_user_bot_error(service: CancelReservationInOdoo, context: Context, house):
    service._members_repo = Mock(get_bot_user=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.user_id = None

    result = service.select_user(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_user
    assert str(result.failure().exc) == 'ERR'


def test_select_user_bot_fail(service: CancelReservationInOdoo, context: Context, house):
    service._members_repo = Mock(get_bot_user=Mock(return_value=Nothing))
    context.house = house
    context.user_id = None

    result = service.select_user(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_user


def test_select_user_bot_ok(service: CancelReservationInOdoo, context: Context, house, user):
    service._members_repo = Mock(get_bot_user=Mock(return_value=Some(user)))
    context.house = house
    context.user_id = None

    result = service.select_user(context)
    assert is_successful(result)
    assert result.unwrap().user == user


def test_cancel_quotation_for_missed_quotation_id(
    service: CancelReservationInOdoo, context: Context, house, reservation
):
    context.house = house
    context.reservation = attr.evolve(reservation, quotation_id=None)
    context.api = Mock(cancel_quotation=Mock(side_effect=RuntimeError('ERR')))

    result = service.cancel_quotation(context)
    assert is_successful(result)

    context.api.cancel_quotation.assert_not_called()


def test_cancel_quotation_error(service: CancelReservationInOdoo, context: Context, house, reservation):
    context.house = house
    context.reservation = reservation
    context.api = Mock(cancel_quotation=Mock(side_effect=RuntimeError('ERR')))

    result = service.cancel_quotation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_cancel_quotation_ok(service: CancelReservationInOdoo, context: Context, house, reservation):
    context.house = house
    context.reservation = reservation
    context.api = Mock(cancel_quotation=Mock(return_value=None))

    result = service.cancel_quotation(context)
    assert is_successful(result)

    context.api.cancel_quotation.assert_called_once_with(reservation.quotation_id)


def test_cancel_opportunity_for_missed_opportunity_id(
    service: CancelReservationInOdoo, context: Context, house, reservation
):
    context.house = house
    context.reservation = attr.evolve(reservation, opportunity_id=None)
    context.api = Mock(cancel_opportunity=Mock(side_effect=RuntimeError('ERR')))

    result = service.cancel_opportunity(context)
    assert is_successful(result)

    context.api.cancel_opportunity.assert_not_called()


def test_cancel_opportunity_error(service: CancelReservationInOdoo, context: Context, house, reservation):
    context.house = house
    context.reservation = reservation
    context.api = Mock(cancel_opportunity=Mock(side_effect=RuntimeError('ERR')))

    result = service.cancel_opportunity(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_cancel_opportunity_ok(service: CancelReservationInOdoo, context: Context, house, reservation):
    context.house = house
    context.reservation = reservation
    context.api = Mock(cancel_opportunity=Mock(return_value=None))

    result = service.cancel_opportunity(context)
    assert is_successful(result)

    context.api.cancel_opportunity.assert_called_once_with(reservation.opportunity_id, CrmLostReasons.EXPENSIVE)


def test_success(service: CancelReservationInOdoo, house, reservation, user):
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))
    service._reservations_repo = Mock(get=Mock(return_value=Some(reservation)))
    service._members_repo = Mock(get_user_by_id=Mock(return_value=Some(user)))
    service.get_rpc_api = Mock(
        return_value=Mock(cancel_opportunity=Mock(return_value=None), cancel_quotation=Mock(return_value=None))
    )

    result = service.execute(house.id, reservation.id, user_id=user.id)
    assert is_successful(result)
    assert result.unwrap()
