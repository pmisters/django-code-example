import datetime
from typing import Union

from board import tasks
from board.value_objects import ReservationCancelEvent, ReservationCreateEvent, ReservationUpdateEvent
from channels import tasks as channel_tasks
from events import EventListener
from invoices.value_objects import ReservationFinanceEvent


class OccupancyHandler(EventListener):
    listens_for = [ReservationCreateEvent, ReservationUpdateEvent, ReservationCancelEvent]

    def handle(
        self,
        event: str,
        *args,
        house_id: int = None,
        roomtype_id: int = None,
        start_date: Union[datetime.date, str] = None,
        end_date: Union[datetime.date, str] = None,
        request_id: str = None,
        pk: int = None,
        **kwargs
    ) -> None:
        if house_id is None:
            return
        # Background operations
        channel_tasks.update_inventory.delay(
            hid=house_id, start_date=start_date, end_date=end_date, request_id=request_id
        )
        # At moment operations
        tasks.calculate_occupancy(hid=house_id, rid=roomtype_id, start_date=start_date, end_date=end_date)
        tasks.update_reservations(hid=house_id, pk=pk)


class ReservationCreateHandler(EventListener):
    listens_for = [ReservationCreateEvent]

    def handle(self, event: str, *args, house_id: int = None, pk: int = None, user_id: int = None, **kwargs) -> None:
        if house_id is None or pk is None:
            return
        tasks.register_reservation_in_odoo.delay(house_id, pk, user_id=user_id)


class ReservationCancelHandler(EventListener):
    listens_for = [ReservationCancelEvent]

    def handle(self, event: str, *args, house_id: int = None, pk: int = None, user_id: int = None, **kwargs) -> None:
        if house_id is None or pk is None:
            return
        tasks.cancel_reservation_in_odoo.delay(house_id, pk, user_id=user_id)


class ReservationUpdateHandler(EventListener):
    listens_for = [ReservationUpdateEvent]

    def handle(self, event: str, *args, house_id: int = None, pk: int = None, user_id: int = None, **kwargs) -> None:
        if house_id is None or pk is None:
            return
        tasks.update_reservation_in_odoo.delay(house_id, pk, user_id=user_id)


class ReservationFinanceHandler(EventListener):
    listens_for = [ReservationFinanceEvent]

    def handle(self, event: str, *args, house_id: int = None, pk: int = None, **kwargs) -> None:
        if house_id is None or pk is None:
            return
        tasks.update_reservations.delay(hid=house_id, pk=pk)
