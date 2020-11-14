from decimal import Decimal
from typing import Any, Dict, List, TYPE_CHECKING, Tuple

from django import http
from django.views.generic import TemplateView

from board.permissions import Permissions
from board.usecases import ShowPricesForm
from board.value_objects import ReservationErrors
from common import functions as cf
from common.loggers import Logger
from common.mixins import AjaxServiceMixin

if TYPE_CHECKING:
    from board.entities import ReservationRoom
    from board.value_objects import ReservationPricesUpdateContext
    from cancelations.entities import Policy
    from common.value_objects import CaseError
    from house_prices.entities import RatePlan
    from houses.entities import House, Room, RoomType


class UpdatePricesFormView(AjaxServiceMixin, TemplateView):
    http_method_names = ['get']
    permissions = [Permissions.RESERVATION_UPDATE]
    template_name = 'board/update_prices_form.html'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._start_date = None
        self._end_date = None

    def get(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        self._start_date = cf.get_date_or_none(request.GET.get('sd'), dayfirst=True)  # noqa
        self._end_date = cf.get_date_or_none(request.GET.get('fd'), dayfirst=True)  # noqa
        return self.process_usecase(
            ShowPricesForm, self.kwargs['hid'], self.kwargs['pk'], self.kwargs['rid'], request.user
        )

    def render_failure(self, failure: 'CaseError', **kwargs) -> http.HttpResponse:
        Logger.warning(__name__, str(failure))
        if failure.failure in (ReservationErrors.missed_house, ReservationErrors.missed_reservation):
            raise http.Http404(failure.error)
        return http.HttpResponseServerError()

    def render_success(self, ctx: 'ReservationPricesUpdateContext' = None, **kwargs) -> http.HttpResponse:
        self._start_date = self._start_date or ctx.reservation_room.checkin
        self._end_date = self._end_date or ctx.reservation_room.checkout
        context = self.get_context_data(ctx)
        return self.render_to_response(context)

    def get_context_data(self, ctx: 'ReservationPricesUpdateContext', **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update(ctx.asdict())
        context['rooms'] = self.prepare_rooms(ctx.rooms, ctx.room_types)
        context['policies'] = self.prepare_policies(ctx.policies, ctx.rate_plans)
        context['totals'] = self.calculate_totals(ctx.reservation_room, ctx.house)
        context['start_date'] = self._start_date
        context['end_date'] = self._end_date
        context['nights'] = (self._end_date - self._start_date).days
        context['prices'] = self.prepare_prices(ctx.reservation_room)
        return context

    @staticmethod
    def prepare_rooms(rooms: List['Room'], room_types: List['RoomType']) -> List[Tuple[int, str]]:
        _room_types = {x.id: x.name for x in room_types}
        result = [(x.id, f"{x.name} / {_room_types.get(x.roomtype_id, '---')}") for x in rooms]
        return sorted(result, key=lambda x: x[1])

    @staticmethod
    def prepare_policies(policies: List['Policy'], plans: List['RatePlan']) -> Dict[int, str]:
        if not policies or not plans:
            return {}
        _policies = {x.id: x.name for x in policies}
        return {
            x.id: _policies[x.policy_id]
            for x in plans
            if x.policy_id is not None and x.policy_id > 0 and x.policy_id in _policies
        }

    def prepare_prices(self, reservation_room: 'ReservationRoom') -> list:
        day_prices = {x.day: x for x in reservation_room.day_prices}
        result = []
        for day in cf.get_days_for_period(self._start_date, self._end_date, exclude=True):
            result.append(day_prices[day] if day in day_prices else {'day': day})
        return result

    @staticmethod
    def calculate_totals(reservation_room: 'ReservationRoom', house: 'House') -> Dict[str, Decimal]:
        original_subtotal = sum([x.price_original or Decimal(0) for x in reservation_room.day_prices])
        original_taxes = sum([x.tax or Decimal(0) for x in reservation_room.day_prices])

        accepted_subtotal = sum([x.price_accepted or Decimal(0) for x in reservation_room.day_prices])
        accepted_taxes = accepted_subtotal * house.tax / Decimal(100) if house.tax > 0 else Decimal(0)

        return {
            'original_subtotal': original_subtotal,
            'original_taxes': original_taxes,
            'original_total': original_subtotal + original_taxes,
            'accepted_subtotal': accepted_subtotal,
            'accepted_taxes': accepted_taxes,
            'accepted_total': accepted_subtotal + accepted_taxes,
        }
