import dataclasses
from typing import Any, Callable, ClassVar, Dict, List

import pytz
from dateutil import relativedelta
from django import http
from django.utils import timezone
from returns.maybe import Nothing
from returns.pipeline import is_successful
from returns.result import Success

from common import functions as cf
from common.http import json_response
from common.value_objects import CaseError, ResultE
from odoo import OdooRPCAPI, get_rpc_api


class DataContextMixin:
    def asdict(self) -> dict:
        result = []
        for f in dataclasses.fields(self):  # noqa
            value = getattr(self, f.name)
            result.append((f.name, value))
        return dict(result)


# Usecase Mixins

class CalendarMixin:
    @staticmethod
    def get_calendar_period(ctx: dataclasses.dataclass) -> ResultE[dataclasses.dataclass]:
        if ctx.base_date is None:
            ctx.base_date = timezone.localdate(
                timezone=pytz.timezone(ctx.house.timezone or cf.get_config('TIME_ZONE'))
            )
        ctx.start_date = ctx.base_date + relativedelta.relativedelta(days=-2)
        ctx.end_date = ctx.base_date + relativedelta.relativedelta(months=1, days=2)
        return Success(ctx)


class HouseSelectMixin:
    _error: Callable
    _houses_repo: ClassVar
    _case_errors: dataclasses.dataclass

    def select_house(self, ctx: dataclasses.dataclass) -> ResultE[dataclasses.dataclass]:
        """Select house from Repository"""
        house_id = cf.get_int_or_none(ctx.house_id) or 0
        if house_id <= 0:
            return self._error('Missed House ID', ctx, self._case_errors.missed_house)
        try:
            data = self._houses_repo.get(
                house_id, company_id=ctx.user.company.id if hasattr(ctx, 'user') and ctx.user is not None else None
            )
        except Exception as err:
            return self._error(f"Error select House ID={house_id}", ctx, self._case_errors.error, exc=err)
        if data == Nothing:
            return self._error(f"Unknown House ID={house_id}", ctx, self._case_errors.missed_house)
        ctx.house = data.unwrap()
        return Success(ctx)


class RatePlanSelectMixin:
    _error: Callable
    _prices_repo: ClassVar
    _case_errors: dataclasses.dataclass

    def select_rate_plan(self, ctx: dataclasses.dataclass) -> ResultE[dataclasses.dataclass]:
        plan_id = cf.get_int_or_none(ctx.plan_id) or 0
        if plan_id <= 0:
            return self._error('Missed Rate Plan ID', ctx, self._case_errors.missed_rateplan)
        try:
            data = self._prices_repo.get_plan(ctx.house.odoo_id, plan_id, user=ctx.user)
        except Exception as err:
            return self._error(
                f"Error select Rate Plan ID={plan_id} for House ID={ctx.house.id}",
                ctx,
                self._case_errors.error,
                exc=err,
            )
        if data == Nothing:
            return self._error(
                f"Unknown Rate Plan ID={plan_id} in House ID={ctx.house.id}", ctx, self._case_errors.missed_rateplan
            )
        ctx.rate_plan = data.unwrap()
        return Success(ctx)


class ReservationSelectMixin:
    _error: Callable
    _reservations_repo: ClassVar
    _case_errors: dataclasses.dataclass

    def select_reservation(self, ctx: dataclasses.dataclass) -> ResultE[dataclasses.dataclass]:
        """Select reservation from Repository and check if it is acceptable"""
        pk = cf.get_int_or_none(ctx.pk) or 0
        if pk <= 0:
            return self._error('Missed Reservation ID', ctx, self._case_errors.missed_reservation)
        try:
            data = self._reservations_repo.get(pk)
        except Exception as err:
            return self._error(f"Error select Reservation ID={pk}", ctx, self._case_errors.error, exc=err)
        if data == Nothing:
            return self._error(f"Unknown Reservation ID={pk}", ctx, self._case_errors.missed_reservation)
        if hasattr(ctx, 'source'):
            ctx.source = data.unwrap()
        else:
            ctx.reservation = data.unwrap()
        return Success(ctx)


class RoomTypeSelectMixin:
    _error: Callable
    _roomtypes_repo: ClassVar
    _case_errors: dataclasses.dataclass

    def select_room_type(self, ctx: dataclasses.dataclass) -> ResultE[dataclasses.dataclass]:
        pk = cf.get_int_or_none(ctx.roomtype_id) or 0
        if pk <= 0:
            return self._error('Wrong Room Type ID', ctx, self._case_errors.missed_roomtype)
        try:
            data = self._roomtypes_repo.get(ctx.house, pk, user=ctx.user)
        except Exception as err:
            return self._error(f"Error select Room Type ID={pk}", ctx, self._case_errors.error, exc=err)
        if data == Nothing:
            return self._error(f"Unknown Room Type ID={pk}", ctx, self._case_errors.missed_roomtype)
        ctx.room_type = data.unwrap()
        return Success(ctx)


class RoomSelectMixin:
    _error: Callable
    _rooms_repo: ClassVar
    _case_errors: dataclasses.dataclass

    def select_room(self, ctx: dataclasses.dataclass) -> ResultE[dataclasses.dataclass]:
        pk = cf.get_int_or_none(ctx.room_id) or 0
        if pk <= 0:
            return self._error('Missed Room ID', ctx, self._case_errors.missed_room)
        try:
            data = self._rooms_repo.get(pk)
        except Exception as err:
            return self._error(
                f"Error select Room ID={pk} in House ID={ctx.house.id}", ctx, self._case_errors.error, exc=err
            )
        if data == Nothing:
            return self._error(
                f"Unknown Room ID={pk} in House ID={ctx.house.id}", ctx, self._case_errors.missed_room
            )
        ctx.room = data.unwrap()
        if ctx.room.house_id != ctx.house.id:
            return self._error(
                f"Unknown Room ID={pk} in House ID={ctx.house.id}", ctx, self._case_errors.missed_room
            )
        return Success(ctx)


class OdooApiMixin:

    @staticmethod
    def get_rpc_api(ctx: dataclasses.dataclass) -> OdooRPCAPI:
        return get_rpc_api(ctx.user) if ctx.api is None else ctx.api


# Views Mixins

class AjaxServiceMixin:
    kwargs: ClassVar
    permissions: ClassVar[List[str]]

    def dispatch(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        if not self.check_access(request):
            return http.HttpResponseForbidden('Access denied!')
        return super().dispatch(request, *args, **kwargs)  # noqa

    def check_access(self, request: http.HttpRequest) -> bool:
        if self.permissions is None or not self.permissions:
            return True
        return all([request.user.check_perms(x, house_id=self.kwargs.get('hid')) for x in self.permissions])  # noqa

    def process_usecase(self, usecase_class: Callable, *args, **kwargs) -> http.HttpResponse:
        result = usecase_class().execute(*args, **kwargs)
        if is_successful(result):
            return self.render_success(result.unwrap(), **kwargs)
        return self.render_failure(result.failure())

    def render_success(self, ctx: Any = None, **kwargs) -> http.HttpResponse:
        return self.as_json({'status': 'OK'})

    def render_failure(self, failure: CaseError, **kwargs) -> http.HttpResponse:
        return http.HttpResponseServerError()

    def json_success(self, data: Dict[str, Any] = None) -> http.HttpResponse:
        payload = {'status': 'OK'}
        if data is not None:
            payload.update(data)
        return self.as_json(payload)

    def json_error(self, error: str = None, data: Dict[str, Any] = None) -> http.HttpResponse:
        payload = {'status': 'ERR'}
        if error is not None:
            payload['error'] = error
        if data is not None:
            payload.update(data)
        return self.as_json(payload)

    @staticmethod
    def as_json(data: Any) -> http.HttpResponse:
        return json_response(data)
