from typing import Any, TYPE_CHECKING

from django import http
from django.views.generic import View

from board.permissions import Permissions
from board.usecases import AcceptReservationChanges
from board.value_objects import ReservationErrors, ReservationUpdateEvent
from common import functions as cf
from common.loggers import Logger
from common.mixins import AjaxServiceMixin

if TYPE_CHECKING:
    from board.entities import Reservation
    from common.value_objects import CaseError


class VerifyFormSaveView(AjaxServiceMixin, View):
    http_method_names = ['post']
    permissions = [Permissions.RESERVATION_UPDATE]

    def post(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        price_ids = [cf.get_int_or_none(x) for x in request.POST.getlist('price_verify')]  # noqa
        price_ids = [x for x in price_ids if x is not None and x > 0]

        return self.process_usecase(
            AcceptReservationChanges, self.kwargs['hid'], self.kwargs['pk'], request.user, price_ids=price_ids
        )

    def render_success(self, ctx: 'Reservation' = None, **kwargs) -> http.HttpResponse:
        ReservationUpdateEvent.dispatch(
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
