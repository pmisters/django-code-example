from typing import Any, List, TYPE_CHECKING

from django import http
from django.urls import reverse
from django.views.generic import View
from pydantic import ValidationError
from returns.maybe import Maybe, Nothing, Some

from board.permissions import Permissions
from board.usecases import CreateReservation
from board.value_objects import ReservationCreateEvent, ReservationErrors, ReservationRequest
from common import functions as cf
from common.i18n import translate as _
from common.loggers import Logger
from common.mixins import AjaxServiceMixin

if TYPE_CHECKING:
    from board.entities import Reservation
    from common.value_objects import CaseError


class ReservationCreateView(AjaxServiceMixin, View):
    http_method_names = ['post']
    permissions = [Permissions.RESERVATION_CREATE]

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

        self._reservation = None

    def post(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        data = request.POST.dict()  # noqa

        value = self.load_reservation_request()
        if value == Nothing:
            return http.HttpResponseServerError()
        self._reservation = value.unwrap()

        self._reservation.plan_id = cf.get_int_or_none(data.get('plan')) or 0
        if self._reservation.plan_id <= 0:
            return self.json_error(_('agenda:plan:error'))

        self._reservation.rate_id = cf.get_int_or_none(data.get('rate'))
        if self._reservation.rate_id <= 0:
            return self.json_error(_('agenda:rate:error'))

        try:
            self.assign_prices_to_reservation(request.POST.getlist('prices'))  # noqa
        except (IndexError, AssertionError):
            return self.json_error(_('agenda:price:error'))

        return self.process_usecase(CreateReservation, self.kwargs['hid'], self._reservation, request.user)

    def render_success(self, ctx: 'Reservation' = None, **kwargs) -> http.HttpResponse:
        ReservationCreateEvent.dispatch(
            house_id=ctx.house_id,
            roomtype_id=self._reservation.roomtype_id,
            start_date=ctx.checkin,
            end_date=ctx.checkout,
            pk=ctx.id,
            user_id=self.request.user.id,
        )
        self.clear_session()
        return self.json_success({'url': reverse('board:reservation', kwargs={'hid': ctx.house_id, 'pk': ctx.id})})

    def render_failure(self, failure: 'CaseError', **kwargs) -> http.HttpResponse:
        Logger.warning(__name__, str(failure))
        if failure.failure in (
            ReservationErrors.missed_house,
            ReservationErrors.missed_roomtype,
            ReservationErrors.missed_rateplan,
            ReservationErrors.missed_rate,
        ):
            raise http.Http404(failure.error)
        return http.HttpResponseServerError()

    def assign_prices_to_reservation(self, data: List[Any]) -> None:
        prices = [cf.get_decimal_or_none(x) for x in data]
        prices = [x for x in prices if x is not None]
        if len(prices) != (self._reservation.checkout - self._reservation.checkin).days:
            raise AssertionError('Count of prices is not equal night count in reservation')
        days = cf.get_days_for_period(self._reservation.checkin, self._reservation.checkout, exclude=True)
        for i, x in enumerate(days):
            self._reservation.prices[x] = prices[i]

    def clear_session(self) -> None:
        try:
            del self.request.session['NEWRES']
        except KeyError:
            pass

    def load_reservation_request(self) -> Maybe[ReservationRequest]:
        try:
            return Some(ReservationRequest.parse_raw(self.request.session.get('NEWRES', '{}')))
        except (ValidationError, ValueError) as err:
            Logger.warning(__name__, f"Error load reservation request from session: {err}")
            return Nothing
