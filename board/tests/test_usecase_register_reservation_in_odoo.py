import datetime
from decimal import Decimal
from unittest.mock import Mock

import attr
import pytest
from django.utils import timezone
from returns.maybe import Nothing, Some
from returns.pipeline import is_successful
from returns.result import Failure, Success

from board.entities import Reservation, ReservationDay, ReservationRoom
from board.usecases._register_reservation_in_odoo import Context, RegisterReservationInOdoo  # noqa
from board.value_objects import ReservationErrors
from common.value_objects import CaseError
from contacts.entities import Contact
from effective_tours.constants import ReservationSources, ReservationStatuses
from odoo.value_objects import CrmStages, CrmTeams, DATE_FORMAT, CrmTags


@pytest.fixture()
def service() -> RegisterReservationInOdoo:
    return RegisterReservationInOdoo()


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
        netto_price=Decimal(3360),
        guest_name='John',
        guest_surname='Smith',
        guest_email='john@efft.com',
        guest_phone='+1-234-567890',
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


def test_missed_house_id(service: RegisterReservationInOdoo, context: Context):
    context.house_id = None

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_error(service: RegisterReservationInOdoo, context: Context):
    service._houses_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_house_fail(service: RegisterReservationInOdoo, context: Context):
    service._houses_repo = Mock(get=Mock(return_value=Nothing))

    result = service.select_house(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_house


def test_select_house_ok(service: RegisterReservationInOdoo, context: Context, house):
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))

    result = service.select_house(context)
    assert is_successful(result)
    assert result.unwrap().house == house


def test_select_reservation_missed_pk(service: RegisterReservationInOdoo, context: Context, house):
    context.house = house
    context.pk = None

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_error(service: RegisterReservationInOdoo, context: Context, house):
    service._reservations_repo = Mock(get=Mock(side_effect=RuntimeError('ERR')))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_select_reservation_fail(service: RegisterReservationInOdoo, context: Context, house):
    service._reservations_repo = Mock(get=Mock(return_value=Nothing))
    context.house = house

    result = service.select_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_select_reservation_ok(service: RegisterReservationInOdoo, context: Context, house, reservation):
    service._reservations_repo = Mock(get=Mock(return_value=Some(reservation)))
    context.house = house

    result = service.select_reservation(context)
    assert is_successful(result)
    assert result.unwrap().reservation == reservation


def test_check_reservation_wrong_house(service: RegisterReservationInOdoo, context: Context, house, reservation):
    context.house = house
    context.reservation = attr.evolve(reservation, house_id=999)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_reservation


def test_check_reservation_room_close(service: RegisterReservationInOdoo, context: Context, house, reservation):
    context.house = house
    context.reservation = attr.evolve(reservation, status=ReservationStatuses.CLOSE)

    result = service.check_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.room_close_reservation


def test_select_user_error(service: RegisterReservationInOdoo, context: Context, house):
    service._members_repo = Mock(get_user_by_id=Mock(side_effect=RuntimeError('ERR')))
    context.house = house

    result = service.select_user(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_user
    assert str(result.failure().exc) == 'ERR'


def test_select_user_fail(service: RegisterReservationInOdoo, context: Context, house):
    service._members_repo = Mock(get_user_by_id=Mock(return_value=Nothing))
    context.house = house

    result = service.select_user(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_user


def test_select_user_ok(service: RegisterReservationInOdoo, context: Context, house, user):
    service._members_repo = Mock(get_user_by_id=Mock(return_value=Some(user)))
    context.house = house

    result = service.select_user(context)
    assert is_successful(result)
    assert result.unwrap().user == user


def test_select_user_bot_error(service: RegisterReservationInOdoo, context: Context, house):
    service._members_repo = Mock(get_bot_user=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.user_id = None

    result = service.select_user(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_user
    assert str(result.failure().exc) == 'ERR'


def test_select_user_bot_fail(service: RegisterReservationInOdoo, context: Context, house):
    service._members_repo = Mock(get_bot_user=Mock(return_value=Nothing))
    context.house = house
    context.user_id = None

    result = service.select_user(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_user


def test_select_user_bot_ok(service: RegisterReservationInOdoo, context: Context, house, user):
    service._members_repo = Mock(get_bot_user=Mock(return_value=Some(user)))
    context.house = house
    context.user_id = None

    result = service.select_user(context)
    assert is_successful(result)
    assert result.unwrap().user == user


def test_create_guest_contact_has_guest_contact_id(
    mocker, service: RegisterReservationInOdoo, context: Context, house, reservation
):
    mocker.patch('contacts.usecases.CreateContact.execute', return_value=Failure(CaseError(error='ERR')))
    context.house = house
    context.reservation = attr.evolve(reservation, guest_contact_id=123)

    result = service.create_guest_contact(context)
    assert is_successful(result)


def test_create_guest_contact_fail(mocker, service: RegisterReservationInOdoo, context: Context, house, reservation):
    mocker.patch('contacts.usecases.CreateContact.execute', return_value=Failure(CaseError(error='ERR')))
    context.house = house
    context.reservation = reservation

    result = service.create_guest_contact(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert result.failure().error == 'ERR'


def test_create_guest_contact_ok(mocker, service: RegisterReservationInOdoo, context: Context, house, reservation):
    mocker.patch('contacts.usecases.CreateContact.execute', return_value=Success(Contact(id=123, name='XXX')))
    context.house = house
    context.reservation = reservation

    result = service.create_guest_contact(context)
    assert is_successful(result)
    assert result.unwrap().reservation.guest_contact_id == 123
    assert result.unwrap().reservation.guest_contact_ids == [123]


def test_create_guest_contact_no_guest_name(service: RegisterReservationInOdoo, context: Context, house, reservation):
    context.house = house
    context.reservation = attr.evolve(reservation, guest_name='', guest_surname='')

    result = service.create_guest_contact(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_guest


def test_create_guest_contact_no_guest_email(
    service: RegisterReservationInOdoo, context: Context, house, reservation
):
    context.house = house
    context.reservation = attr.evolve(reservation, guest_email='')

    result = service.create_guest_contact(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.missed_guest


def test_create_opportunity_has_opportunity_id(
    service: RegisterReservationInOdoo, context: Context, house, reservation
):
    context.house = house
    context.reservation = attr.evolve(reservation, opportunity_id=123)
    context.api = Mock(create_opportunity=Mock(side_effect=RuntimeError('ERR')))

    result = service.create_opportunity(context)
    assert is_successful(result)

    context.api.create_opportunity.assert_not_called()


def test_create_opportuniry_error(service: RegisterReservationInOdoo, context: Context, house, reservation):
    context.house = house
    context.reservation = reservation
    context.api = Mock(create_opportunity=Mock(side_effect=RuntimeError('ERR')))

    result = service.create_opportunity(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_create_opportunity_fail(service: RegisterReservationInOdoo, context: Context, house, reservation):
    context.house = house
    context.reservation = reservation
    context.api = Mock(create_opportunity=Mock(return_value=Nothing))

    result = service.create_opportunity(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert result.failure().error.startswith('Error create Opportunity for Reservation ID=')


def test_create_opportunity_ok(service: RegisterReservationInOdoo, context: Context, house, reservation):
    context.house = house
    context.reservation = attr.evolve(reservation, guest_contact_id=222)
    context.api = Mock(create_opportunity=Mock(return_value=Some(123)))

    result = service.create_opportunity(context)
    assert is_successful(result)
    assert result.unwrap().reservation.opportunity_id == 123

    context.api.create_opportunity.assert_called_once_with(
        {
            'company_id': house.odoo_id,
            'name': reservation.get_opportunity_name(),
            'partner_id': 222,
            'planned_revenue': '3360',
            'stage_id': CrmStages.NEGOTIATION.value,
            'team_id': CrmTeams.SALES.value,
            'tag_ids': [CrmTags.DIRECT.value],
        },
        context={'default_type': 'opportunity'},
    )


def test_create_quotation_has_quotation_id(service: RegisterReservationInOdoo, context: Context, house, reservation):
    context.house = house
    context.reservation = attr.evolve(reservation, quotation_id=123)
    context.api = Mock(create_quotation=Mock(side_effect=RuntimeError('ERR')))

    result = service.create_quotation(context)
    assert is_successful(result)

    context.api.create_quotation.assert_not_called()


def test_create_quotation_error(service: RegisterReservationInOdoo, context: Context, house, reservation, user):
    context.house = house
    context.user = user
    context.reservation = attr.evolve(reservation, guest_contact_id=222, opportunity_id=333)
    context.api = Mock(create_quotation=Mock(side_effect=RuntimeError('ERR')))

    result = service.create_quotation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_create_quotation_fail(service: RegisterReservationInOdoo, context: Context, house, reservation, user):
    context.house = house
    context.user = user
    context.reservation = attr.evolve(reservation, guest_contact_id=222, opportunity_id=333)
    context.api = Mock(create_quotation=Mock(return_value=Nothing))

    result = service.create_quotation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert result.failure().error.startswith('Error create Quotation for Reservation ID=')


def test_create_quotation_ok(
    service: RegisterReservationInOdoo, context: Context, house, reservation, room_type, user
):
    context.house = house
    context.user = user
    context.reservation = attr.evolve(reservation, guest_contact_id=222, opportunity_id=333)
    context.api = Mock(create_quotation=Mock(return_value=Some(123)))

    result = service.create_quotation(context)
    assert is_successful(result)
    assert result.unwrap().reservation.quotation_id == 123

    context.api.create_quotation.assert_called_once_with(
        {
            'partner_id': 222,
            'partner_invoice_id': 222,
            'partner_shipping_id': 222,
            'user_id': user.odoo_id,
            'currency_id': house.currency.odoo_id,
            'note': '',
            'company_id': house.odoo_id,
            'team_id': CrmTeams.SALES.value,
            'opportunity_id': 333,
            'report_grids': True,
            'origin': reservation.id,
            'client_order_ref': '',
        },
        [
            {
                'price_unit': '1120',
                'order_partner_id': 222,
                'discount': 0.,
                'product_id': room_type.id,
                'product_uom_qty': 1,
                'item_date': reservation.checkin.strftime(DATE_FORMAT),
            },
            {
                'price_unit': '1120',
                'order_partner_id': 222,
                'discount': 0.,
                'product_id': room_type.id,
                'product_uom_qty': 1,
                'item_date': (reservation.checkin + datetime.timedelta(days=1)).strftime(DATE_FORMAT),
            },
            {
                'price_unit': '1120',
                'order_partner_id': 222,
                'discount': 0.,
                'product_id': room_type.id,
                'product_uom_qty': 1,
                'item_date': (reservation.checkin + datetime.timedelta(days=2)).strftime(DATE_FORMAT),
            },
        ]
    )


def test_save_reservation_error(service: RegisterReservationInOdoo, context: Context, house, reservation):
    service._reservations_repo = Mock(save=Mock(side_effect=RuntimeError('ERR')))
    context.house = house
    context.reservation = reservation

    result = service.save_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.error
    assert str(result.failure().exc) == 'ERR'


def test_save_reservation_fail(service: RegisterReservationInOdoo, context: Context, house, reservation):
    service._reservations_repo = Mock(save=Mock(return_value=(Nothing, False)))
    context.house = house
    context.reservation = reservation

    result = service.save_reservation(context)
    assert not is_successful(result)
    assert result.failure().failure == ReservationErrors.save
    assert result.failure().error.startswith('Error save Reservation')


def test_save_reservation_ok(service: RegisterReservationInOdoo, context: Context, house, reservation):
    _reservation = attr.evolve(reservation, guest_contact_id=123)
    service._reservations_repo = Mock(save=Mock(return_value=(Some(_reservation), True)))
    context.house = house
    context.reservation = reservation

    result = service.save_reservation(context)
    assert is_successful(result)
    assert result.unwrap().reservation == _reservation


def test_success(mocker, service: RegisterReservationInOdoo, house, reservation, user):
    _reservation = attr.evolve(reservation, guest_contact_id=123)
    api = Mock(create_opportunity=Mock(return_value=Some(333)), create_quotation=Mock(return_value=Some(444)))
    contact_call = mocker.patch(
        'contacts.usecases.CreateContact.execute', return_value=Success(Contact(id=123, name='XXX'))
    )
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))
    service._members_repo = Mock(get_user_by_id=Mock(return_value=Some(user)))
    service._reservations_repo = Mock(
        get=Mock(return_value=Some(reservation)), save=Mock(return_value=(Some(_reservation), True))
    )
    service.get_rpc_api = Mock(return_value=api)

    result = service.execute(house.id, reservation.id, user_id=user.id)
    assert is_successful(result)

    contact_call.assert_called_once()
    api.create_opportunity.assert_called_once()
    api.create_quotation.assert_called_once()
