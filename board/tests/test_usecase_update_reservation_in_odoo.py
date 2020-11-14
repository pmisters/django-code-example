import datetime
from decimal import Decimal
from unittest.mock import Mock

import attr
import pytest
from django.utils import timezone
from returns.maybe import Nothing, Some
from returns.pipeline import is_successful

from board.entities import Reservation, ReservationDay, ReservationRoom
from board.usecases._update_reservation_in_odoo import Context, UpdateReservationInOdoo  # noqa
from board.value_objects import ReservationErrors
from effective_tours.constants import ReservationSources, ReservationStatuses
from odoo.value_objects import DATE_FORMAT


@pytest.fixture()
def service() -> UpdateReservationInOdoo:
    return UpdateReservationInOdoo()


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
        price=Decimal(3360),
        price_accepted=Decimal(3360),
        netto_price=Decimal(3360),
        netto_price_accepted=Decimal(3360),
        guest_name='John',
        guest_surname='Smith',
        guest_email='john@efft.com',
        guest_phone='+1-234-567890',
        opportunity_id=123,
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
                price=Decimal(3360),
                netto_price=Decimal(3360),
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
    return Context(house_id=house.id, pk=reservation.id, user_id=user.id)


def test_missed_house_id(service: UpdateReservationInOdoo, context: Context):
    context.house_id = None

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_error(service: UpdateReservationInOdoo, context: Context):
    service._houses_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_house_fail(service: UpdateReservationInOdoo, context: Context):
    service._houses_repo = Mock(get=Mock(return_value=Nothing))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_ok(service: UpdateReservationInOdoo, context: Context, house):
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))

    result = service.select_house(context)
    assert is_successful(result)
    assert result.unwrap().house == house


def test_select_reservation_missed_pk(service: UpdateReservationInOdoo, context: Context, house):
    context.house = house
    context.pk = None

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_error(service: UpdateReservationInOdoo, context: Context, house):
    service._reservations_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_reservation_fail(service: UpdateReservationInOdoo, context: Context, house):
    service._reservations_repo = Mock(get=Mock(return_value=Nothing))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_ok(service: UpdateReservationInOdoo, context: Context, house, reservation):
    service._reservations_repo = Mock(get=Mock(return_value=Some(reservation)))
    context.house = house

    result = service.select_reservation(context)
    assert is_successful(result)
    assert result.unwrap().reservation == reservation


def test_check_reservation_wrong_house(service: UpdateReservationInOdoo, context: Context, house, reservation):
    context.house = house
    context.reservation = attr.evolve(reservation, house_id=999)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_check_reservation_room_close(service: UpdateReservationInOdoo, context: Context, house, reservation):
    context.house = house
    context.reservation = attr.evolve(reservation, status=ReservationStatuses.CLOSE)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.room_close_reservation


def test_select_user_error(service: UpdateReservationInOdoo, context: Context, house):
    service._members_repo = Mock(get_user_by_id=Mock(side_effect=RuntimeError('ERR')))
    context.house = house

    result = service.select_user(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_user
    assert str(result.failure().exc) == 'ERR'


def test_select_user_fail(service: UpdateReservationInOdoo, context: Context, house):
    service._members_repo = Mock(get_user_by_id=Mock(return_value=Nothing))
    context.house = house

    result = service.select_user(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_user


def test_select_user_ok(service: UpdateReservationInOdoo, context: Context, house, user):
    service._members_repo = Mock(get_user_by_id=Mock(return_value=Some(user)))
    context.house = house

    result = service.select_user(context)
    assert is_successful(result)
    assert result.unwrap().user == user


def test_select_user_bot_error(service: UpdateReservationInOdoo, context: Context, house):
    service._members_repo = Mock(get_bot_user=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.user_id = None

    result = service.select_user(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_user
    assert str(result.failure().exc) == 'ERR'


def test_select_user_bot_fail(service: UpdateReservationInOdoo, context: Context, house):
    service._members_repo = Mock(get_bot_user=Mock(return_value=Nothing))
    context.house = house
    context.user_id = None

    result = service.select_user(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_user


def test_select_user_bot_ok(service: UpdateReservationInOdoo, context: Context, house, user):
    service._members_repo = Mock(get_bot_user=Mock(return_value=Some(user)))
    context.house = house
    context.user_id = None

    result = service.select_user(context)
    assert is_successful(result)
    assert result.unwrap().user == user


def test_update_opportunity_if_no_opportunity_id(
    service: UpdateReservationInOdoo, context: Context, house, user, reservation
):
    context.house = house
    context.user = user
    context.reservation = attr.evolve(reservation, opportunity_id=None)
    context.api = Mock(update_opportunity=Mock(side_effect=RuntimeError('ERR')))

    result = service.update_opportunity(context)
    assert is_successful(result)

    context.api.update_opportunity.assert_not_called()


def test_update_opportunity_error(service: UpdateReservationInOdoo, context: Context, house, user, reservation):
    context.house = house
    context.user = user
    context.reservation = reservation
    context.api = Mock(update_opportunity=Mock(side_effect=RuntimeError('ERR')))

    result = service.update_opportunity(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_update_opportunity_ok(service: UpdateReservationInOdoo, context: Context, house, user, reservation):
    context.house = house
    context.user = user
    context.reservation = reservation
    context.api = Mock(update_opportunity=Mock(return_value=None))

    result = service.update_opportunity(context)
    assert is_successful(result)

    context.api.update_opportunity.assert_called_once_with(
        123, {'name': reservation.get_opportunity_name(), 'planned_revenue': '3360'}
    )


def test_check_need_update_quotation_no_quotation_id(
    service: UpdateReservationInOdoo, context: Context, house, user, reservation
):
    context.house = house
    context.user = user
    context.reservation = attr.evolve(reservation, quotation_id=None)
    context.api = Mock(get_quotation_items=Mock(side_effect=RuntimeError('ERR')))

    result = service.check_need_update_quotation(context)
    assert is_successful(result)
    assert not result.unwrap().is_need_update_quotation

    context.api.get_quotation_items.assert_not_called()


def test_check_need_update_quotation_error(
    service: UpdateReservationInOdoo, context: Context, house, user, reservation
):
    context.house = house
    context.user = user
    context.reservation = reservation
    context.api = Mock(get_quotation_items=Mock(side_effect=RuntimeError('ERR')))

    result = service.check_need_update_quotation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_check_need_update_quotation_equal(
    service: UpdateReservationInOdoo, context: Context, house, user, reservation, room_type
):
    context.house = house
    context.user = user
    context.reservation = reservation
    context.api = Mock(
        get_quotation_items=Mock(
            return_value=[
                {
                    'id': 1230,
                    'product_id': [room_type.id, room_type.name],
                    'item_date': datetime.date.today().strftime(DATE_FORMAT),
                    'product_uom_qty': 1.0,
                    'price_unit': 1120.0,
                },
                {
                    'id': 1231,
                    'product_id': [room_type.id, room_type.name],
                    'item_date': (datetime.date.today() + datetime.timedelta(days=1)).strftime(DATE_FORMAT),
                    'product_uom_qty': 1.0,
                    'price_unit': 1120.0,
                },
                {
                    'id': 1232,
                    'product_id': [room_type.id, room_type.name],
                    'item_date': (datetime.date.today() + datetime.timedelta(days=2)).strftime(DATE_FORMAT),
                    'product_uom_qty': 1.0,
                    'price_unit': 1120.0,
                },
            ]
        )
    )

    result = service.check_need_update_quotation(context)
    assert is_successful(result)
    assert not result.unwrap().is_need_update_quotation


def test_check_need_update_quotation_different(
    service: UpdateReservationInOdoo, context: Context, house, user, reservation, room_type
):
    context.house = house
    context.user = user
    context.reservation = reservation
    context.api = Mock(
        get_quotation_items=Mock(
            return_value=[
                {
                    'id': 1230,
                    'product_id': [room_type.id, room_type.name],
                    'item_date': datetime.date.today().strftime(DATE_FORMAT),
                    'product_uom_qty': 1.0,
                    'price_unit': 1120.0,
                },
                {
                    'id': 1231,
                    'product_id': [room_type.id, room_type.name],
                    'item_date': (datetime.date.today() + datetime.timedelta(days=1)).strftime(DATE_FORMAT),
                    'product_uom_qty': 1.0,
                    'price_unit': 1120.0,
                },
                {
                    'id': 1232,
                    'product_id': [room_type.id, room_type.name],
                    'item_date': (datetime.date.today() + datetime.timedelta(days=2)).strftime(DATE_FORMAT),
                    'product_uom_qty': 1.0,
                    'price_unit': 1000.0,
                },
            ]
        )
    )

    result = service.check_need_update_quotation(context)
    assert is_successful(result)
    assert result.unwrap().is_need_update_quotation


def test_get_quotation_state_no_need_update(
    service: UpdateReservationInOdoo, context: Context, house, user, reservation
):
    context.house = house
    context.user = user
    context.reservation = reservation
    context.is_need_update_quotation = False
    context.api = Mock(get_quotation=Mock(side_effect=RuntimeError('ERR')))

    result = service.get_quotation_state(context)
    assert is_successful(result)
    assert not result.unwrap().is_locked_quotation

    context.api.get_quotation.assert_not_called()


def test_get_quotation_state_error(service: UpdateReservationInOdoo, context: Context, house, user, reservation):
    context.house = house
    context.user = user
    context.reservation = reservation
    context.is_need_update_quotation = True
    context.api = Mock(get_quotation=Mock(side_effect=RuntimeError('ERR')))

    result = service.get_quotation_state(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_get_quotation_state_fail(service: UpdateReservationInOdoo, context: Context, house, user, reservation):
    context.house = house
    context.user = user
    context.reservation = reservation
    context.is_need_update_quotation = True
    context.api = Mock(get_quotation=Mock(return_value=Nothing))

    result = service.get_quotation_state(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert result.failure().error.startswith('Missed Quotation ID=')


def test_get_quotation_state_ok_locked(service: UpdateReservationInOdoo, context: Context, house, user, reservation):
    context.house = house
    context.user = user
    context.reservation = reservation
    context.is_need_update_quotation = True
    context.api = Mock(get_quotation=Mock(return_value=Some(Mock(id=321, state='done'))))

    result = service.get_quotation_state(context)
    assert is_successful(result)
    assert result.unwrap().is_locked_quotation

    context.api.get_quotation.assert_called_once_with(321)


def test_get_quotation_state_ok_not_locked(
    service: UpdateReservationInOdoo, context: Context, house, user, reservation
):
    context.house = house
    context.user = user
    context.reservation = reservation
    context.is_need_update_quotation = True
    context.api = Mock(get_quotation=Mock(return_value=Some(Mock(id=321, state='draft'))))

    result = service.get_quotation_state(context)
    assert is_successful(result)
    assert not result.unwrap().is_locked_quotation

    context.api.get_quotation.assert_called_once_with(321)


def test_unlock_quotation_no_need_update(
    service: UpdateReservationInOdoo, context: Context, house, user, reservation
):
    context.house = house
    context.user = user
    context.reservation = reservation
    context.is_need_update_quotation = False
    context.api = Mock(unlock_quotation=Mock(side_effect=RuntimeError('ERR')))

    result = service.unlock_quotation(context)
    assert is_successful(result)

    context.api.unlock_quotation.assert_not_called()


def test_unlock_quotation_not_locked(service: UpdateReservationInOdoo, context: Context, house, user, reservation):
    context.house = house
    context.user = user
    context.reservation = reservation
    context.is_need_update_quotation = True
    context.is_locked_quotation = False
    context.api = Mock(unlock_quotation=Mock(side_effect=RuntimeError('ERR')))

    result = service.unlock_quotation(context)
    assert is_successful(result)

    context.api.unlock_quotation.assert_not_called()


def test_unlock_quotation_error(service: UpdateReservationInOdoo, context: Context, house, user, reservation):
    context.house = house
    context.user = user
    context.reservation = reservation
    context.is_need_update_quotation = True
    context.is_locked_quotation = True
    context.api = Mock(unlock_quotation=Mock(side_effect=RuntimeError('ERR')))

    result = service.unlock_quotation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_unlock_quotation_ok(service: UpdateReservationInOdoo, context: Context, house, user, reservation):
    context.house = house
    context.user = user
    context.reservation = reservation
    context.is_need_update_quotation = True
    context.is_locked_quotation = True
    context.api = Mock(unlock_quotation=Mock(return_value=None))

    result = service.unlock_quotation(context)
    assert is_successful(result)

    context.api.unlock_quotation.assert_called_once_with(321)


def test_update_quotation_no_need_update(
    service: UpdateReservationInOdoo, context: Context, house, user, reservation
):
    context.house = house
    context.user = user
    context.reservation = reservation
    context.is_need_update_quotation = False
    context.api = Mock(update_quotation_items=Mock(side_effect=RuntimeError('ERR')))

    result = service.update_quotation(context)
    assert is_successful(result)

    context.api.update_quotation_items.assert_not_called()


def test_update_quotation_error(service: UpdateReservationInOdoo, context: Context, house, user, reservation):
    context.house = house
    context.user = user
    context.reservation = reservation
    context.is_need_update_quotation = True
    context.api = Mock(update_quotation_items=Mock(side_effect=RuntimeError('ERR')))

    result = service.update_quotation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_update_quotation_ok(service: UpdateReservationInOdoo, context: Context, house, user, reservation, room_type):
    context.house = house
    context.user = user
    context.reservation = reservation
    context.is_need_update_quotation = True
    context.api = Mock(update_quotation_items=Mock(return_value=None))

    result = service.update_quotation(context)
    assert is_successful(result)

    context.api.update_quotation_items.assert_called_once_with(
        321,
        [
            {
                'product_id': room_type.id,
                'item_date': datetime.date.today().strftime(DATE_FORMAT),
                'product_uom_qty': 1.0,
                'price_unit': 1120.0,
            },
            {
                'product_id': room_type.id,
                'item_date': (datetime.date.today() + datetime.timedelta(days=1)).strftime(DATE_FORMAT),
                'product_uom_qty': 1.0,
                'price_unit': 1120.0,
            },
            {
                'product_id': room_type.id,
                'item_date': (datetime.date.today() + datetime.timedelta(days=2)).strftime(DATE_FORMAT),
                'product_uom_qty': 1.0,
                'price_unit': 1120.0,
            },
        ]
    )


def test_lock_back_quotation_no_need_update(
    service: UpdateReservationInOdoo, context: Context, house, user, reservation
):
    context.house = house
    context.user = user
    context.reservation = reservation
    context.is_need_update_quotation = False
    context.is_locked_quotation = True
    context.api = Mock(confirm_quotation=Mock(side_effect=RuntimeError('ERR')))

    result = service.lock_back_quotation(context)
    assert is_successful(result)

    context.api.confirm_quotation.assert_not_called()


def test_lock_back_quotation_wasnot_locked(
    service: UpdateReservationInOdoo, context: Context, house, user, reservation
):
    context.house = house
    context.user = user
    context.reservation = reservation
    context.is_need_update_quotation = True
    context.is_locked_quotation = False
    context.api = Mock(confirm_quotation=Mock(side_effect=RuntimeError('ERR')))

    result = service.lock_back_quotation(context)
    assert is_successful(result)

    context.api.confirm_quotation.assert_not_called()


def test_lock_back_quotation_error(service: UpdateReservationInOdoo, context: Context, house, user, reservation):
    context.house = house
    context.user = user
    context.reservation = reservation
    context.is_need_update_quotation = True
    context.is_locked_quotation = True
    context.api = Mock(confirm_quotation=Mock(side_effect=RuntimeError('ERR')))

    result = service.lock_back_quotation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_lock_back_quotation_ok(service: UpdateReservationInOdoo, context: Context, house, user, reservation):
    context.house = house
    context.user = user
    context.reservation = reservation
    context.is_need_update_quotation = True
    context.is_locked_quotation = True
    context.api = Mock(confirm_quotation=Mock(return_value=None))

    result = service.lock_back_quotation(context)
    assert is_successful(result)

    context.api.confirm_quotation.assert_called_once_with(321)


def test_success_draft_quotation(service: UpdateReservationInOdoo, house, user, reservation):
    api = Mock(
        update_opportunity=Mock(return_value=None),
        get_quotation_items=Mock(return_value=[]),
        get_quotation=Mock(return_value=Some(Mock(id=321, state='draft'))),
        unlock_quotation=Mock(return_value=None),
        confirm_quotation=Mock(return_value=None),
        update_quotation_items=Mock(return_value=None),
    )
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))
    service._reservations_repo = Mock(get=Mock(return_value=Some(reservation)))
    service._members_repo = Mock(get_user_by_id=Mock(return_value=Some(user)))
    service.get_rpc_api = Mock(return_value=api)

    result = service.execute(house.id, reservation.id, user_id=user.id)
    assert is_successful(result)

    api.update_opportunity.assert_called_once()
    api.get_quotation_items.assert_called_once()
    api.get_quotation.assert_called_once()
    api.unlock_quotation.assert_not_called()
    api.update_quotation_items.assert_called_once()
    api.confirm_quotation.assert_not_called()


def test_success_locked_quotation(service: UpdateReservationInOdoo, house, user, reservation):
    api = Mock(
        update_opportunity=Mock(return_value=None),
        get_quotation_items=Mock(return_value=[]),
        get_quotation=Mock(return_value=Some(Mock(id=321, state='done'))),
        unlock_quotation=Mock(return_value=None),
        confirm_quotation=Mock(return_value=None),
        update_quotation_items=Mock(return_value=None),
    )
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))
    service._reservations_repo = Mock(get=Mock(return_value=Some(reservation)))
    service._members_repo = Mock(get_user_by_id=Mock(return_value=Some(user)))
    service.get_rpc_api = Mock(return_value=api)

    result = service.execute(house.id, reservation.id, user_id=user.id)
    assert is_successful(result)

    api.update_opportunity.assert_called_once()
    api.get_quotation_items.assert_called_once()
    api.get_quotation.assert_called_once()
    api.unlock_quotation.assert_called_once()
    api.update_quotation_items.assert_called_once()
    api.confirm_quotation.assert_called_once()


def test_success_not_changed_quotation(service: UpdateReservationInOdoo, house, user, reservation, room_type):
    api = Mock(
        update_opportunity=Mock(return_value=None),
        get_quotation_items=Mock(
            return_value=[
                {
                    'id': 1230,
                    'product_id': [room_type.id, room_type.name],
                    'item_date': datetime.date.today().strftime(DATE_FORMAT),
                    'product_uom_qty': 1.0,
                    'price_unit': 1120.0,
                },
                {
                    'id': 1231,
                    'product_id': [room_type.id, room_type.name],
                    'item_date': (datetime.date.today() + datetime.timedelta(days=1)).strftime(DATE_FORMAT),
                    'product_uom_qty': 1.0,
                    'price_unit': 1120.0,
                },
                {
                    'id': 1232,
                    'product_id': [room_type.id, room_type.name],
                    'item_date': (datetime.date.today() + datetime.timedelta(days=2)).strftime(DATE_FORMAT),
                    'product_uom_qty': 1.0,
                    'price_unit': 1120.0,
                },
            ]
        ),
        get_quotation=Mock(return_value=Some(Mock(id=321, state='draft'))),
        unlock_quotation=Mock(return_value=None),
        confirm_quotation=Mock(return_value=None),
        update_quotation_items=Mock(return_value=None),
    )
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))
    service._reservations_repo = Mock(get=Mock(return_value=Some(reservation)))
    service._members_repo = Mock(get_user_by_id=Mock(return_value=Some(user)))
    service.get_rpc_api = Mock(return_value=api)

    result = service.execute(house.id, reservation.id, user_id=user.id)
    assert is_successful(result)

    api.update_opportunity.assert_called_once()
    api.get_quotation_items.assert_called_once()
    api.get_quotation.assert_not_called()
    api.unlock_quotation.assert_not_called()
    api.update_quotation_items.assert_not_called()
    api.confirm_quotation.assert_not_called()
