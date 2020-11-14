import datetime
from unittest.mock import Mock

import attr
import pytest
from returns.maybe import Nothing, Some
from returns.pipeline import is_successful

from board.usecases._calculate_occupancy import CalculateOccupancy, Context  # noqa
from board.value_objects import OccupancyErrors


@pytest.fixture()
def service():
    return CalculateOccupancy()


@pytest.fixture()
def context(house, room_type):
    return Context(
        house_id=house.id,
        roomtype_id=room_type.id,
        start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=1),
    )


def test_select_houses_all_error(service, context):
    service._houses_repo = Mock(select=Mock(side_effect=RuntimeError("ERR")))
    context.house_id = None

    result = service.select_houses(context)
    assert not is_successful(result)
    assert result.failure().failure == OccupancyErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_houses_all_ok(service, context, house):
    house2 = attr.evolve(house, id=111)
    service._houses_repo = Mock(select=Mock(return_value=[house, house2]))
    context.house_id = None

    result = service.select_houses(context)
    assert is_successful(result)
    assert result.unwrap().houses == [house, house2]


def test_select_houses_one_error(service, context):
    service._houses_repo = Mock(get=Mock(side_effect=RuntimeError("ERR")))

    result = service.select_houses(context)
    assert not is_successful(result)
    assert result.failure().failure == OccupancyErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_houses_one_fail(service, context):
    service._houses_repo = Mock(get=Mock(return_value=Nothing))

    result = service.select_houses(context)
    assert not is_successful(result)
    assert result.failure().failure == OccupancyErrors.missed_house


def test_select_houses_one_ok(service, context, house):
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))

    result = service.select_houses(context)
    assert is_successful(result)
    assert result.unwrap().houses == [house]


def test_select_company_bots_no_houses(service, context):
    context.houses = []

    result = service.select_company_bots(context)
    assert is_successful(result)
    assert result.unwrap().users == {}


def test_select_company_bots_error(service, context, house):
    service._members_repo = Mock(search_users=Mock(side_effect=RuntimeError("ERR")))
    context.houses = [house]

    result = service.select_company_bots(context)
    assert not is_successful(result)
    assert result.failure().failure == OccupancyErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_company_bots_fail(service, context, house):
    service._members_repo = Mock(search_users=Mock(return_value=[]))
    context.houses = [house]

    result = service.select_company_bots(context)
    assert not is_successful(result)
    assert result.failure().failure == OccupancyErrors.missed_user


def test_select_company_bots_ok(service, context, house, user):
    service._members_repo = Mock(search_users=Mock(return_value=[user]))
    context.houses = [house]

    result = service.select_company_bots(context)
    assert is_successful(result)
    assert result.unwrap().users == {house.company.id: user}


def test_select_roomtypes_no_houses(service, context):
    context.houses = []
    context.users = {}
    context.roomtype_id = None

    result = service.select_roomtypes(context)
    assert is_successful(result)
    assert result.unwrap().room_types == {}


def test_select_roomtypes_all_error(service, context, house, user):
    service._roomtypes_repo = Mock(select=Mock(side_effect=RuntimeError("ERR")))
    context.houses = [house]
    context.users = {house.company.id: user}
    context.roomtype_id = None

    result = service.select_roomtypes(context)
    assert not is_successful(result)
    assert result.failure().failure == OccupancyErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_roomtypes_all_ok(service, context, house, user, room_type):
    room_type2 = attr.evolve(room_type, id=999)
    service._roomtypes_repo = Mock(select=Mock(return_value=[room_type, room_type2]))
    context.houses = [house]
    context.users = {house.company.id: user}
    context.roomtype_id = None

    result = service.select_roomtypes(context)
    assert is_successful(result)
    assert result.unwrap().room_types == {house.id: [room_type, room_type2]}


def test_select_roomtypes_one_error(service, context, house, user):
    service._roomtypes_repo = Mock(get=Mock(side_effect=RuntimeError("ERR")))
    context.houses = [house]
    context.users = {house.company.id: user}

    result = service.select_roomtypes(context)
    assert not is_successful(result)
    assert result.failure().failure == OccupancyErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_roomtypes_one_fail(service, context, house, user):
    service._roomtypes_repo = Mock(get=Mock(return_value=Nothing))
    context.houses = [house]
    context.users = {house.company.id: user}

    result = service.select_roomtypes(context)
    assert not is_successful(result)
    assert result.failure().failure == OccupancyErrors.missed_roomtype


def test_select_roomtypes_one_ok(service, context, house, user, room_type):
    service._roomtypes_repo = Mock(get=Mock(return_value=Some(room_type)))
    context.houses = [house]
    context.users = {house.company.id: user}

    result = service.select_roomtypes(context)
    assert is_successful(result)
    assert result.unwrap().room_types == {house.id: [room_type]}


def test_populate_roomtypes_empty(service, context):
    context.room_types = {}

    result = service.populate_roomtypes(context)
    assert is_successful(result)
    assert result.unwrap().room_count == {}


def test_populate_roomtypes_error(service, context, house, room_type):
    service._rooms_repo = Mock(get_count=Mock(side_effect=RuntimeError("ERR")))
    context.houses = [house]
    context.room_types = {house.id: [room_type]}

    result = service.populate_roomtypes(context)
    assert not is_successful(result)
    assert result.failure().failure == OccupancyErrors.error
    assert str(result.failure().exc) == "ERR"


def test_populate_roomtypes_ok(service, context, house, room_type):
    service._rooms_repo = Mock(get_count=Mock(return_value=2))
    context.room_types = {house.id: [room_type]}

    result = service.populate_roomtypes(context)
    assert is_successful(result)
    assert result.unwrap().room_count == {house.id: {room_type.id: 2}}


def test_select_busy_days_empty(service, context):
    context.room_types = {}

    result = service.select_busy_days(context)
    assert is_successful(result)
    assert result.unwrap().busy_days == {}


def test_select_busy_days_error(service, context, house, room_type):
    service._reservations_repo = Mock(select_busy_days=Mock(side_effect=RuntimeError("ERR")))
    context.room_types = {house.id: [room_type]}

    result = service.select_busy_days(context)
    assert not is_successful(result)
    assert result.failure().failure == OccupancyErrors.error
    assert str(result.failure().exc) == "ERR"


def test_select_busy_days_ok(service, context, house, room_type):
    service._reservations_repo = Mock(
        select_busy_days=Mock(
            return_value={room_type.id: {context.start_date: 5, context.start_date + datetime.timedelta(days=1): 4}}
        )
    )
    context.room_types = {house.id: [room_type]}

    result = service.select_busy_days(context)
    assert is_successful(result)
    assert result.unwrap().busy_days == {
        house.id: {room_type.id: {context.start_date: 5, context.start_date + datetime.timedelta(days=1): 4}}
    }


def test_calculate_occupancy_empty(service, context):
    context.room_types = {}

    result = service.calculate_occupancy(context)
    assert is_successful(result)
    assert result.unwrap().occupancies == {}


def test_calculate_occupancy_on(service, context, house, room_type):
    context.room_types = {house.id: [room_type]}
    context.room_count = {house.id: {room_type.id: 5}}
    context.busy_days = {
        house.id: {room_type.id: {datetime.date.today(): 2, datetime.date.today() + datetime.timedelta(days=1): 3}}
    }

    result = service.calculate_occupancy(context)
    assert is_successful(result)
    assert result.unwrap().occupancies == {
        house.id: {room_type.id: {datetime.date.today(): 3, datetime.date.today() + datetime.timedelta(days=1): 2}}
    }


def test_save_error(service, context, house, room_type):
    service._occupancy_repo = Mock(set=Mock(side_effect=RuntimeError("ERR")))
    context.room_types = {house.id: [room_type]}
    context.occupancies = {
        house.id: {room_type.id: {datetime.date.today(): 3, datetime.date.today() + datetime.timedelta(days=1): 2}}
    }

    result = service.save(context)
    assert not is_successful(result)
    assert result.failure().failure == OccupancyErrors.error
    assert str(result.failure().exc) == "ERR"


def test_save_ok(service, context, house, room_type):
    service._occupancy_repo = Mock(set=Mock(return_value=None))
    context.room_types = {house.id: [room_type]}
    context.occupancies = {
        house.id: {room_type.id: {datetime.date.today(): 3, datetime.date.today() + datetime.timedelta(days=1): 2}}
    }

    result = service.save(context)
    assert is_successful(result)


def test_success(service, context, user, house, room_type):
    service._houses_repo = Mock(get=Mock(return_value=Some(house)))
    service._members_repo = Mock(search_users=Mock(return_value=[user]))
    service._roomtypes_repo = Mock(get=Mock(return_value=Some(room_type)))
    service._rooms_repo = Mock(get_count=Mock(return_value=5))
    service._reservations_repo = Mock(select_busy_days=Mock(return_value={room_type.id: {context.start_date: 10}}))
    service._occupancy_repo = Mock(set=Mock(return_value=None))

    result = service.execute(
        house_id=house.id, roomtype_id=room_type.id, start_date=context.start_date, end_date=context.end_date,
    )
    assert is_successful(result)
