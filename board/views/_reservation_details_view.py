import datetime
from typing import Any, Dict, List, TYPE_CHECKING

from django import http
from django.views.generic import TemplateView

from board.permissions import Permissions
from board.usecases import SelectReservation
from board.value_objects import ReservationErrors
from common import functions as cf
from common.http import RenderServerError
from common.loggers import Logger
from common.mixins import AjaxServiceMixin

if TYPE_CHECKING:
    from board.entities import Reservation
    from board.value_objects import ReservationDetailsContext
    from common.value_objects import CaseError


class ReservationDetailsView(AjaxServiceMixin, TemplateView):
    http_method_names = ['get']
    permissions = [Permissions.RESERVATION_READ]
    template_name = 'board/reservation_details.html'

    def get(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        return self.process_usecase(SelectReservation, self.kwargs['hid'], self.kwargs['pk'], request.user)

    def render_success(self, ctx: 'ReservationDetailsContext' = None, **kwargs) -> http.HttpResponse:
        return self.render_to_response(self.get_context_data(ctx=ctx))

    def render_failure(self, failure: 'CaseError', **kwargs) -> http.HttpResponse:
        Logger.warning(__name__, str(failure))
        if failure.failure in (ReservationErrors.missed_house, ReservationErrors.missed_reservation):
            raise http.Http404(failure.error)
        return RenderServerError(request=self.request).do()

    def get_context_data(self, ctx: 'ReservationDetailsContext' = None, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update(ctx.asdict())
        context['CURRENT_HOUSE'] = ctx.house
        context['reservation_rooms'] = self.prepare_rooms(ctx.reservation)
        context['guest_id'] = cf.get_int_or_none(self.request.GET.get('guest_id'))  # noqa
        context['pending_balance'] = ctx.reservation.price_accepted - ctx.payed_amount
        return context

    @staticmethod
    def prepare_rooms(reservation: 'Reservation') -> List[Dict[str, Any]]:
        result = []
        for room in reservation.rooms:
            data = {'room': room, 'periods': []}
            period = {'start_date': None, 'end_date': None, 'room_type': None, 'room': None}
            for price in sorted(room.day_prices, key=lambda x: x.day):
                period['end_date'] = price.day + datetime.timedelta(days=1)
                if period['start_date'] is None:
                    period['start_date'] = price.day

                if period['room_type'] is None:
                    period['room_type'] = price.room_type
                    period['room'] = price.room
                elif period['room_type'] != price.room_type:
                    period['end_date'] = price.day
                    data['periods'].append(period)
                    period = {
                        'start_date': price.day,
                        'end_date': price.day + datetime.timedelta(days=1),
                        'room_type': price.room_type,
                        'room': price.room,
                    }
                elif period['room'] is None and price.room is not None:
                    period['end_date'] = price.day
                    data['periods'].append(period)
                    period = {
                        'start_date': price.day,
                        'end_date': price.day + datetime.timedelta(days=1),
                        'room_type': price.room_type,
                        'room': price.room,
                    }
                elif period['room'] != price.room:
                    period['end_date'] = price.day
                    data['periods'].append(period)
                    period = {
                        'start_date': price.day,
                        'end_date': price.day + datetime.timedelta(days=1),
                        'room_type': price.room_type,
                        'room': price.room,
                    }
            if period['start_date'] is not None:
                data['periods'].append(period)
            result.append(data)
        return result
