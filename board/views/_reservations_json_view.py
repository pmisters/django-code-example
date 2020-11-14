from typing import Any, List, Optional

from django import http
from django.urls import reverse
from django.views.generic import View

from board.permissions import Permissions
from board.usecases import SelectReservations
from board.value_objects import CachedReservation, ReservationErrors
from common import functions as cf
from common.loggers import Logger
from common.mixins import AjaxServiceMixin
from common.value_objects import CaseError

permissions = [Permissions.BOARD_READ, Permissions.RESERVATION_READ]


class ReservationsJsonView(AjaxServiceMixin, View):
    http_method_names = ['get']
    permissions = [Permissions.BOARD_READ, Permissions.RESERVATION_READ]

    def get(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        base_date = cf.get_date_or_none(request.GET.get('bd'))  # noqa
        return self.process_usecase(SelectReservations, self.kwargs['hid'], base_date=base_date)

    def render_success(self, ctx: List[CachedReservation] = None, **kwargs) -> http.HttpResponse:
        data = []
        for reservation in ctx:
            item = reservation.dict()
            item['checkin'] = self.format_dates(item.get('checkin'))
            item['checkout'] = self.format_dates(item.get('checkout'))
            item['source_code'] = item.get('source_code', '').lower()
            if item['status'] != 'close':
                item['url'] = reverse(
                    'board:reservation', kwargs={'hid': self.kwargs['hid'], 'pk': item['reservation_id']}
                )
            else:
                item['url'] = ''
            data.append(item)
        return self.as_json({'data': data})

    def render_failure(self, failure: 'CaseError', **kwargs) -> http.HttpResponse:
        Logger.warning(__name__, str(failure))
        if failure.failure == ReservationErrors.missed_house:
            raise http.Http404(failure.error)
        return http.HttpResponseServerError()

    @staticmethod
    def format_dates(value: Optional[str]) -> Optional[str]:
        dt = cf.get_datetime_or_none(value)
        return dt.strftime('%d/%m/%Y %H:%M') if dt is not None else value
