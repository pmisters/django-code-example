from typing import Any, Dict, Optional, TYPE_CHECKING, Tuple

from django import http
from django.views.generic import View

from board.permissions import Permissions
from board.usecases import MoveReservation
from board.value_objects import ReservationErrors, ReservationUpdateEvent
from common import functions as cf
from common.i18n import translate as _
from common.loggers import Logger
from common.mixins import AjaxServiceMixin

if TYPE_CHECKING:
    from common.value_objects import CaseError


class ReservationMoveView(AjaxServiceMixin, View):
    http_method_names = ['post']
    permissions = [Permissions.RESERVATION_UPDATE]

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self._reservation_id = None

    def post(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        data = request.POST.dict()  # noqa
        pk = data.get('pk', '').strip()
        if pk == '' or '-' not in pk:
            return self.json_error(_('common.error:system'))

        self._reservation_id = cf.get_int_or_none(data.get('rid')) or 0
        if self._reservation_id <= 0:
            return self.json_error(_('agenda:error:unknown_reservation'))

        roomtype_id, room_id = self.parse_rooms(data)

        return self.process_usecase(
            MoveReservation,
            pk,
            self._reservation_id,
            self.kwargs['hid'],
            roomtype_id=roomtype_id,
            room_id=room_id,
            user=request.user,
        )

    @staticmethod
    def parse_rooms(data: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
        grid = data.get('grid', '').strip().lower()
        grid_id = cf.get_int_or_none(data.get('grid_id')) or 0
        if grid == 'roomtype':
            if grid_id <= 0:
                raise http.Http404('Unknown Room Type ID')
            return grid_id, None
        elif grid == 'room':
            if grid_id <= 0:
                raise http.Http404('Unknown Room ID')
            return None, grid_id
        return None, None

    def render_success(self, ctx: Any = None, **kwargs) -> http.HttpResponse:
        ReservationUpdateEvent.dispatch(
            house_id=self.kwargs['hid'], pk=self._reservation_id, user_id=self.request.user.id
        )
        return self.json_success()

    def render_failure(self, failure: 'CaseError', **kwargs) -> http.HttpResponse:
        Logger.warning(__name__, str(failure))
        if failure.failure in (
            ReservationErrors.missed_house,
            ReservationErrors.missed_reservation,
            ReservationErrors.missed_roomtype,
            ReservationErrors.missed_room,
        ):
            raise http.Http404(failure.error)
        return http.HttpResponseServerError()
