from typing import Any, TYPE_CHECKING

from django import http
from django.views.generic import View

from board.permissions import Permissions
from board.usecases import DeleteRoomClose
from board.value_objects import ReservationCancelEvent, ReservationErrors
from common.loggers import Logger
from common.mixins import AjaxServiceMixin

if TYPE_CHECKING:
    from board.entities import Reservation
    from common.value_objects import CaseError


class RoomCLoseDeleteView(AjaxServiceMixin, View):
    http_method_names = ['post']
    permissions = [Permissions.RESERVATION_DELETE]

    def post(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        pk = request.POST.get('pk', '').strip()  # noqa
        if pk == '' or '-' not in pk:
            raise http.Http404('Missing Reservation ID')
        return self.process_usecase(DeleteRoomClose, pk, self.kwargs['hid'], request.user)

    def render_success(self, ctx: 'Reservation' = None, **kwargs) -> http.HttpResponse:
        ReservationCancelEvent.dispatch(
            house_id=ctx.house_id,
            pk=ctx.id,
            start_date=ctx.checkin,
            end_date=ctx.checkout,
            user_id=self.request.user.id,
        )
        return self.as_json('OK')

    def render_failure(self, failure: 'CaseError', **kwargs) -> http.HttpResponse:
        Logger.warning(__name__, str(failure))
        if failure.failure in (ReservationErrors.missed_house, ReservationErrors.missed_reservation):
            raise http.Http404(failure.error)
        return http.HttpResponseServerError()
