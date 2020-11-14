from decimal import Decimal
from typing import Any, Dict, TYPE_CHECKING, Union

from django import http
from django.views.generic import View
from pydantic import ValidationError
from returns.maybe import Nothing

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


class ReservationCreateRequestView(AjaxServiceMixin, View):
    http_method_names = ['post']
    permissions = [Permissions.RESERVATION_CREATE]

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

        self._reservation = None

    def post(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        data = self.parse_reservation_date_from_input(request.POST.dict())  # noqa
        if isinstance(data, http.HttpResponse):
            return data
        self._reservation = data

        return self.process_usecase(
            CalculateNewReservation,
            self.kwargs['hid'],
            self._reservation.roomtype_id,
            self._reservation.plan_id,
            self._reservation.checkin,
            self._reservation.checkout,
            self._reservation.guests,
            request.user,
        )

    def render_success(self, ctx: 'ReservationCalcContext' = None, **kwargs) -> http.HttpResponse:
        self._reservation.rate_id = ctx.rate.id if ctx.rate is not None else None
        self.request.session['NEWRES'] = self._reservation.json()
        return self.json_success({'data': self.make_content_for_form(ctx)})

    def render_failure(self, failure: 'CaseError', **kwargs) -> http.HttpResponse:
        Logger.warning(__name__, str(failure))
        if failure.failure in (
            ReservationErrors.missed_house, ReservationErrors.missed_roomtype, ReservationErrors.missed_rateplan
        ):
            raise http.Http404(failure.error)
        return http.HttpResponseServerError()

    def parse_reservation_date_from_input(self, data: Dict[str, Any]) -> Union[http.HttpResponse, ReservationRequest]:
        roomtype_id = cf.get_int_or_none(data.get('room_type')) or 0
        if roomtype_id <= 0:
            return self.json_error(_('agenda:room_type:error'))
        plan_id = cf.get_int_or_none(data.get('plan')) or 0
        if plan_id <= 0:
            return self.json_error(_('agenda:plan:error'))
        period = cf.parse_period(data.get('period', ''))
        if period == Nothing:
            return self.json_error(_('agenda:period:error'))
        start_date, end_date = period.unwrap()
        guest_count = cf.get_int_or_none(data.get('guest_count')) or 0
        if guest_count <= 0:
            return self.json_error(_('agenda:guest_count:error'))
        try:
            reservation = ReservationRequest(
                roomtype_id=roomtype_id,
                plan_id=plan_id,
                checkin=start_date,
                checkout=end_date,
                guests=guest_count,
                guest_name=data.get('guest_name', '').strip(),
                guest_surname=data.get('guest_surname', '').strip(),
                guest_email=data.get('guest_email', '').strip(),
                guest_phone=self.parse_phone(data),
                notes=data.get('notes', '').strip(),
            )
        except ValidationError as err:
            Logger.warning(__name__, f"Error create a new Reservation Request: {err}")
            return http.HttpResponseServerError()
        return reservation

    @staticmethod
    def parse_phone(data: Dict[str, Any]) -> str:
        code = data.get('guest_phone_code', '').strip()
        if code != '':
            code = f"+{code}"
        return '-'.join([code, data.get('guest_phone', '')]).strip('-')

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
