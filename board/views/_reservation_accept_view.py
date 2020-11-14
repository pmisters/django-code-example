from typing import Any, TYPE_CHECKING

from django import http
from django.views.generic import View
from django.views.generic.base import ContextMixin

from board.permissions import Permissions
from board.usecases import AcceptHoldReservation
from board.value_objects import ReservationErrors, ReservationUpdateEvent
from common import functions as cf
from common.loggers import Logger
from common.mixins import AjaxServiceMixin

if TYPE_CHECKING:
    from common.value_objects import CaseError


class ReservationAcceptView(AjaxServiceMixin, ContextMixin, View):
    http_method_names = ['post']
    permissions = [Permissions.RESERVATION_UPDATE]

    def post(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        pk = cf.get_int_or_none(self.kwargs.get('pk')) or 0
        if pk <= 0:
            raise http.Http404('Wrong or missed Reservation ID')
        return self.process_usecase(AcceptHoldReservation, self.kwargs.get('hid'), pk, request.user)

    def render_success(self, ctx: Any = None, **kwargs) -> http.HttpResponse:
        ReservationUpdateEvent.dispatch(
            house_id=self.kwargs['hid'], pk=self.kwargs['pk'], user_id=self.request.user.id
        )
        return super().render_success(ctx)

    def render_failure(self, failure: 'CaseError', **kwargs) -> http.HttpResponse:
        Logger.warning(__name__, str(failure))
        if failure.failure in (ReservationErrors.missed_house, ReservationErrors.missed_reservation):
            raise http.Http404(failure.error)
        return super().render_failure(failure)
