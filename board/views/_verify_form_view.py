from typing import Any, TYPE_CHECKING

from django import http
from django.views.generic import TemplateView

from board.permissions import Permissions
from board.usecases import ShowVerifyForm
from board.value_objects import ReservationErrors
from common.loggers import Logger
from common.mixins import AjaxServiceMixin

if TYPE_CHECKING:
    from board.value_objects import ReservationVerifyContext
    from common.value_objects import CaseError


class VerifyFormView(AjaxServiceMixin, TemplateView):
    http_method_names = ['get']
    permissions = [Permissions.RESERVATION_UPDATE]
    template_name = 'board/verify_form.html'

    def get(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        return self.process_usecase(ShowVerifyForm, self.kwargs['hid'], self.kwargs['pk'], request.user)

    def render_success(self, ctx: 'ReservationVerifyContext' = None, **kwargs) -> http.HttpResponse:
        return self.render_to_response(self.get_context_data(**ctx.asdict()))

    def render_failure(self, failure: 'CaseError', **kwargs) -> http.HttpResponse:
        Logger.warning(__name__, str(failure))
        if failure.failure in (ReservationErrors.missed_house, ReservationErrors.missed_reservation):
            raise http.Http404(failure.error)
        return http.HttpResponseServerError()
