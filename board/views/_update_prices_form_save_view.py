import datetime
import re
from typing import Any, Dict, TYPE_CHECKING

from django import http
from django.views.generic import View

from board.permissions import Permissions
from board.usecases import UpdateReservationPrices
from board.value_objects import ReservationErrors, ReservationUpdateEvent
from common import functions as cf
from common.i18n import translate as _
from common.loggers import Logger
from common.mixins import AjaxServiceMixin

if TYPE_CHECKING:
    from board.entities import Reservation


class UpdatePricesFormSaveView(AjaxServiceMixin, View):
    http_method_names = ['post']
    permissions = [Permissions.RESERVATION_UPDATE]

    def post(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        data = request.POST.dict()  # noqa
        plan_id = cf.get_int_or_none(data.get('rate_plan')) or 0
        if plan_id <= 0:
            return self.json_error(_('agenda:plan:error'))
        return self.process_usecase(
            UpdateReservationPrices,
            self.kwargs['hid'],
            self.kwargs['pk'],
            self.kwargs['rid'],
            plan_id,
            request.user,
            self.parse_price_data(data),
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

    def render_failure(self, failure: Any, **kwargs) -> http.HttpResponse:
        Logger.warning(__name__, failure)
        if failure.failure in (ReservationErrors.missed_house, ReservationErrors.missed_reservation):
            raise http.Http404(failure.error)
        elif failure.failure == ReservationErrors.missed_rateplan:
            return self.json_error(_('agenda:plan:error'))
        elif failure.failure == ReservationErrors.wrong_period:
            return self.json_error(_('agenda:error:ota_update_period'))
        return http.HttpResponseServerError()

    @staticmethod
    def parse_price_data(data: Dict[str, Any]) -> Dict[datetime.date, Dict[str, Any]]:
        result = {}
        pattern = re.compile(r'\[(\d{4}-\d{2}-\d{2})]')
        for key, value in data.items():
            if not key.startswith('room[') and not key.startswith('price['):
                continue
            match = pattern.search(key)
            if match is None:
                continue
            day = cf.get_date_or_none(match.group(1))
            if day is None:
                continue
            if day not in result:
                result[day] = {'room': None, 'price': None, 'day': day}
            if key.startswith('room['):
                result[day]['room'] = cf.get_int_or_none(value)
            elif key.startswith('price['):
                result[day]['price'] = cf.get_decimal_or_none(value)
        return result
