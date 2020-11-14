from typing import Any, TYPE_CHECKING

from django import http
from django.views.generic import View
from returns.maybe import Nothing

from board.permissions import Permissions
from board.usecases import CreateRoomClose
from board.value_objects import ReservationCreateEvent, ReservationErrors
from common import functions as cf
from common.i18n import translate as _
from common.loggers import Logger
from common.mixins import AjaxServiceMixin
from effective_tours.constants import RoomCloseReasons

if TYPE_CHECKING:
    from board.entities import Reservation
    from common.value_objects import CaseError


class RoomCloseCreateView(AjaxServiceMixin, View):
    http_method_names = ['post']
    permissions = [Permissions.RESERVATION_CREATE]

    def post(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        data = request.POST.dict()  # noqa
        period = cf.parse_period(data.get('period', ''))
        if period == Nothing:
            return self.json_error(_('agenda:period:error'))
        start_date, end_date = period.unwrap()
        room_id = cf.get_int_or_none(data.get('room')) or 0
        if room_id <= 0:
            return self.json_error(_('agenda:room:error'))
        reason = RoomCloseReasons.get_by_name(data.get('status', ''))
        if reason is None:
            return self.json_error(_('agenda:status:error'))
        notes = data.get('notes', '')

        return self.process_usecase(
            CreateRoomClose, self.kwargs['hid'], room_id, start_date, end_date, reason, request.user, notes=notes
        )

    def render_success(self, ctx: 'Reservation' = None, **kwargs) -> http.HttpResponse:
        ReservationCreateEvent.dispatch(
            house_id=self.kwargs['hid'],
            pk=ctx.id,
            start_date=ctx.checkin,
            end_date=ctx.checkout,
            user_id=self.request.user.id,
        )
        return self.json_success()

    def render_failure(self, failure: 'CaseError', **kwargs) -> http.HttpResponse:
        Logger.warning(__name__, str(failure))
        if failure.failure in (ReservationErrors.missed_house, ReservationErrors.missed_room):
            raise http.Http404(failure.error)
        elif failure.failure == ReservationErrors.busy_room:
            return self.json_error(_('agenda:error:busy_room'))
        return http.HttpResponseServerError()
