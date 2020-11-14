from typing import Any, TYPE_CHECKING

from django import http
from django.views.generic import View

from board.permissions import Permissions
from board.usecases import CancelReservation
from board.value_objects import ReservationCancelEvent, ReservationErrors
from common import functions as cf
from common.loggers import Logger
from common.mixins import AjaxServiceMixin

if TYPE_CHECKING:
    from board.entities import Reservation
    from common.value_objects import CaseError


class ReservationCancelView(AjaxServiceMixin, View):
    http_method_names = ['post']
    permissions = [Permissions.RESERVATION_DELETE]

    def post(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        pk = cf.get_int_or_none(self.kwargs['pk']) or 0
        if pk <= 0:
            raise http.Http404('Missed or wrong Reservation ID')
        return self.process_usecase(CancelReservation, self.kwargs['hid'], pk, request.user)

    def render_success(self, ctx: 'Reservation' = None, **kwargs) -> http.HttpResponse:
        ReservationCancelEvent.dispatch(
            house_id=ctx.house_id,
            pk=ctx.id,
            start_date=ctx.checkin,
            end_date=ctx.checkout,
            user_id=self.request.user.id,
        )
        return self.json_success()

    def render_failure(self, failure: 'CaseError', **kwargs) -> http.HttpResponse:
        Logger.warning(__name__, str(failure))
        if failure.failure in (ReservationErrors.missed_house, ReservationErrors.missed_reservation):
            raise http.Http404(failure.error)
        return http.HttpResponseServerError()
