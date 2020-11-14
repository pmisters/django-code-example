from typing import Any, Dict, List, TYPE_CHECKING, Tuple

from django import http
from django.http import Http404
from django.views.generic import TemplateView

from board.permissions import Permissions
from board.usecases import ShowCalendar
from board.value_objects import CalendarErrors
from common import functions as cf
from common.http import RenderServerError
from common.loggers import Logger
from common.mixins import AjaxServiceMixin
from effective_tours.constants import RoomCloseReasons
from houses.permissions import Permissions as HousePermissions

if TYPE_CHECKING:
    from board.value_objects import CalendarContext
    from common.value_objects import CaseError
    from houses.entities import Room, RoomTypeDetails


class CalendarView(AjaxServiceMixin, TemplateView):
    http_method_names = ['get']
    permissions = [
        Permissions.BOARD_READ,
        HousePermissions.HOUSE_READ,
        HousePermissions.ROOMTYPE_READ,
        HousePermissions.ROOM_READ,
    ]
    template_name = 'board/calendar.html'

    def get(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        start_date = cf.get_date_or_none(request.GET.get('sd'))  # noqa
        return self.process_usecase(ShowCalendar, self.kwargs['hid'], start_date, user=request.user)

    def render_success(self, ctx: 'CalendarContext' = None, **kwargs) -> http.HttpResponse:
        return self.render_to_response(self.get_context_data(ctx=ctx))

    def render_failure(self, failure: 'CaseError', **kwargs) -> http.HttpResponse:
        Logger.warning(__name__, str(failure))
        if failure.failure == CalendarErrors.missed_house:
            raise Http404(failure.error)
        return RenderServerError(request=self.request).do()

    def get_context_data(self, ctx: 'CalendarContext' = None, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update(ctx.asdict())
        context['house'] = context['CURRENT_HOUSE'] = ctx.house
        context['structure'] = self.prepare_structure(ctx.room_types, ctx.rooms)
        context['close_reasons'] = RoomCloseReasons.choices()
        try:
            context['close_rooms'] = self.prepare_close_rooms(ctx.rooms, ctx.room_types)
        except Exception as err:
            Logger.warning(__name__, f"Error select Rooms for House ID={ctx.house.id} : {err}")
        return context

    @staticmethod
    def prepare_structure(room_types: List["RoomTypeDetails"], rooms: List["Room"]) -> List[Dict[str, Any]]:
        result = []
        for room_type in room_types:
            result.append(
                {
                    'name': room_type.name,
                    'room_type': room_type,
                    'rooms': [x for x in rooms if x.roomtype_id == room_type.id],
                }
            )
        return result

    @staticmethod
    def prepare_close_rooms(rooms: List["Room"], room_types: List["RoomTypeDetails"]) -> List[Tuple[int, str]]:
        _room_types = {x.id: x for x in room_types}
        result = []
        for room in rooms:
            if room.roomtype_id in _room_types:
                name = f"{room.name} / {_room_types[room.roomtype_id].name}"
            else:
                name = room.name
            result.append((room.id, name))
        return sorted(result, key=lambda x: x[1])
