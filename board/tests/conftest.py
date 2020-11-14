from decimal import Decimal
from unittest.mock import Mock

import inject
import pytest

from action_logger.repositories import ChangelogRepo
from board.repositories import OccupancyRepo, ReservationsCacheRepo, ReservationsRepo
from cancelations.entities import Policy, PolicyItem
from cancelations.repositories import PoliciesRepo
from contacts.repositores import ContactsRepo
from discounts.repositories import DiscountsRepo
from effective_tours.constants import CompanyTypes, PolicyChargeTypes
from geo.repositories import GeoRepo
from house_prices.entities import Rate, RatePlan
from house_prices.repositories import PricesRepo
from houses.entities import House, Room, RoomType
from houses.repositories import HousesRepo, RoomTypesRepo, RoomsRepo
from ledger.entities import Currency
from members.entities import Company, User
from members.repositories import MembersRepo


@pytest.yield_fixture(autouse=True)
def set_inject():
    inject.clear_and_configure(
        lambda x: x.bind(ChangelogRepo, Mock())
        .bind(ContactsRepo, Mock())
        .bind(DiscountsRepo, Mock())
        .bind(GeoRepo, Mock())
        .bind(HousesRepo, Mock())
        .bind(MembersRepo, Mock())
        .bind(OccupancyRepo, Mock())
        .bind(PricesRepo, Mock())
        .bind(ReservationsCacheRepo, Mock())
        .bind(ReservationsRepo, Mock())
        .bind(RoomsRepo, Mock())
        .bind(RoomTypesRepo, Mock())
        .bind(PoliciesRepo, Mock())
    )
    yield
    inject.clear()


@pytest.fixture(scope='module')
def company():
    return Company(
        id=100,
        name='COMPANY',
        company_type=CompanyTypes.HOTELIER,
        currency=Currency(id=200, code='USD', odoo_id=200, symbol='$'),
    )


@pytest.fixture(scope='module')
def user(company):
    return User(id=300, company=company, username='test-user', odoo_id=3)


@pytest.fixture(scope='module')
def house(company):
    return House(id=400, name='XXX', company=company, currency=company.currency, odoo_id=111, tax=Decimal(10))


@pytest.fixture(scope='module')
def room_type(house):
    return RoomType(id=100, odoo_company_id=house.odoo_id, name='XXX')


@pytest.fixture(scope='module')
def cancellation_policy(house):
    return Policy(
        id=601,
        house_id=house.id,
        name='Charge for 2 nights in case of cancelation',
        policy_items=[PolicyItem(id=602, policy_id=601, charge=2, charge_type=PolicyChargeTypes.NIGHT, days=None)],
    )


@pytest.fixture(scope='module')
def rate_plan(house, cancellation_policy):
    return RatePlan(id=600, name='NoRefund', odoo_company_id=house.odoo_id, policy_id=cancellation_policy.id)


@pytest.fixture(scope='module')
def rate(rate_plan):
    return Rate(id=700, odoo_company_id=111, odoo_currency_id=200, name='DBL', plan=rate_plan, occupancy=2)


@pytest.fixture(scope='module')
def room(house, room_type):
    return Room(id=800, house_id=house.id, roomtype_id=room_type.id, name='R1')
