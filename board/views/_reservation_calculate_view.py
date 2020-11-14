from decimal import Decimal
from typing import Any, Dict, TYPE_CHECKING

from django import http
from django.views.generic import View
from pydantic import ValidationError
from returns.maybe import Maybe, Nothing, Some

from board.permissions import Permissions
from board.usecases import CalculateNewReservation
from board.value_objects import ReservationErrors, ReservationRequest
from common import functions as cf
from common.i18n import translate as _
from common.loggers import Logger
from common.mixins import AjaxServiceMixin
from ledger.templatetags import ledger_tags

if TYPE_CHECKING:
    from board.value_objects import ReservationCalcContext
    from common.value_objects import CaseError


class ReservationCalculateView(AjaxServiceMixin, View):
    http_method_names = ['get']
    permissions = [Permissions.RESERVATION_CREATE]

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

        self._reservation = None
        self._plan_id = None
        self._rate_id = None

    def get(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        self._plan_id = cf.get_int_or_none(request.GET.get('plan')) or 0  # noqa
        if self._plan_id <= 0:
            return self.json_error(_('agenda:plan:error'))

        data = self.load_reservation_request()
        if data == Nothing:
            return http.HttpResponseServerError()
        self._reservation = data.unwrap()

        self._rate_id = cf.get_int_or_none(request.GET.get('rate'))  # noqa
        if self._plan_id == self._reservation.plan_id and self._rate_id is None:
            self._rate_id = self._reservation.rate_id

        return self.process_usecase(
            CalculateNewReservation,
            self.kwargs['hid'],
            self._reservation.roomtype_id,
            self._plan_id,
            self._reservation.checkin,
            self._reservation.checkout,
            self._reservation.guests,
            request.user,
            rate_id=self._rate_id,
        )

    def render_success(self, ctx: 'ReservationCalcContext' = None, **kwargs) -> http.HttpResponse:
        self._reservation.plan_id = self._plan_id
        self._reservation.rate_id = self._rate_id
        self.request.session['NEWRES'] = self._reservation.json()
        return self.json_success({'data': self.make_content_for_form(ctx)})

    def render_failure(self, failure: 'CaseError', **kwargs) -> http.HttpResponse:
        Logger.warning(__name__, str(failure))
        if failure.failure in (
            ReservationErrors.missed_house, ReservationErrors.missed_roomtype, ReservationErrors.missed_rateplan
        ):
            raise http.Http404(failure.error)
        return http.HttpResponseServerError()

    def load_reservation_request(self) -> Maybe[ReservationRequest]:
        try:
            return Some(ReservationRequest.parse_raw(self.request.session.get('NEWRES', '{}')))
        except (ValidationError, ValueError) as err:
            Logger.warning(__name__, f"Error load reservation request from session: {err}")
            return Nothing

    @staticmethod
    def make_content_for_form(context: 'ReservationCalcContext') -> Dict[str, Any]:
        total_price = cf.round_price(sum([x or Decimal(0) for x in context.prices.values()]))
        taxes = cf.round_price(total_price * context.house.tax / Decimal(100))
        result = {
            'roomtype': context.room_type.name,
            'plan_id': context.rate_plan.id,
            'rates': [(x.id, x.name) for x in sorted(context.rates, key=lambda x: x.name)],
            'rate': context.rate.id if context.rate is not None else None,
            'prices': [
                (x.strftime('%d/%m/%Y'), str(cf.round_price(y or Decimal(0)))) for x, y in context.prices.items()
            ],
            'tax': str(context.house.tax),
            'taxes': ledger_tags.money_format(taxes, context.house.currency),
            'subtotal': ledger_tags.money_format(total_price, context.house.currency),
            'total': ledger_tags.money_format(total_price + taxes, context.house.currency),
        }
        return result
