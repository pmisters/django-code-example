import datetime
from typing import Dict, Optional, TYPE_CHECKING

from django import http
from django.views.decorators.http import require_GET
from returns.pipeline import is_successful

from board import tasks
from board.permissions import Permissions
from board.usecases import SelectOccupancies
from board.value_objects import OccupanciesContext, ReservationErrors
from common import functions as cf
from common.http import json_response
from common.i18n import translate as _
from common.loggers import Logger
from common.value_objects import ResultE

if TYPE_CHECKING:
    from members.entities import User


@require_GET
def occupancies_json_view(request: http.HttpRequest, hid: int) -> http.HttpResponse:
    if not request.user.check_perms(Permissions.BOARD_READ, house_id=hid):  # noqa
        return http.HttpResponseForbidden(_('common:error:access'))
    result = select_occupancies(hid, cf.get_date_or_none(request.GET.get('sd')), request.user)  # noqa
    if is_successful(result):
        return json_response({'data': prepare_occupancies(result.unwrap().occupancies)})

    failure = result.failure()
    Logger.warning(__name__, failure)
    if failure.failure == ReservationErrors.missed_house:
        raise http.Http404(f"Unknown House ID={hid}")
    return http.HttpResponseServerError()


def select_occupancies(hid: int, base_date: Optional[datetime.date], user: 'User') -> ResultE[OccupanciesContext]:
    result = SelectOccupancies().execute(hid, base_date, user=user)
    if not is_successful(result):
        return result
    context = result.unwrap()
    if check_getted_occupancy(context.occupancies):
        return result
    Logger.info(__name__, f"Missed occupancy in Redis for House ID={hid}. Recalculate...")
    tasks.calculate_occupancy(hid=hid, start_date=context.start_date, end_date=context.end_date)
    return SelectOccupancies().execute(pk=hid, base_date=base_date, user=user)


def check_getted_occupancy(occupancies: Dict[int, Dict[datetime.date, Optional[int]]]) -> bool:
    for data in occupancies.values():
        if any([x is None for x in data.values()]):
            return False
    return True


def prepare_occupancies(occupancies: Dict[int, Dict[datetime.date, Optional[int]]]) -> Dict[str, int]:
    result = {}
    for roomtype_id, data in occupancies.items():
        for day, value in data.items():
            result[f'{roomtype_id}-{day.strftime("%Y%m%d")}'] = value or 0
    return result
