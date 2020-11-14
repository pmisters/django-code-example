import datetime
from typing import Union

from celery import shared_task
from returns.pipeline import is_successful

import effective_tours.dependencies  # noqa  For Dependency Injector
from board.usecases import (
    CalculateOccupancy,
    CancelReservationInOdoo,
    RegisterReservationInOdoo,
    UpdateReservationCache,
    UpdateReservationInOdoo,
)
from board.value_objects import ReservationErrors
from common import functions as cf, notifications as nf
from common.loggers import Logger
from invoices.tasks import auto_make_invoice


@shared_task(bind=True, name='board.calculate_occupancy', retry_kwargs={'max_retries': 2})
def calculate_occupancy(
    self,
    hid: int = None,
    rid: int = None,
    start_date: Union[str, datetime.date] = None,
    end_date: Union[str, datetime.date] = None,
) -> None:
    if start_date is not None and not isinstance(start_date, datetime.date):
        start_date = cf.get_date_or_none(start_date)
    if end_date is not None and not isinstance(end_date, datetime.date):
        end_date = cf.get_date_or_none(end_date)
    result = CalculateOccupancy().execute(house_id=hid, roomtype_id=rid, start_date=start_date, end_date=end_date)
    if is_successful(result):
        return
    failure = result.failure()
    Logger.warning(__name__, failure)
    nf.notify_warning(f"Error recalculate occupancy\n{failure.short_info()}")
    raise self.retry(exc=failure.exc)


@shared_task(bind=True, name='board.cancel_reservation_in_odoo', retry_kwargs={'max_retries': 2})
def cancel_reservation_in_odoo(self, hid: int, pk: int, user_id: int = None) -> None:
    result = CancelReservationInOdoo().execute(hid, pk, user_id=user_id)
    if is_successful(result):
        auto_make_invoice.delay(pk)
        return
    failure = result.failure()
    if failure.failure == ReservationErrors.room_close_reservation:
        # It's normal case but use error just for breaking flow
        return
    Logger.warning(__name__, failure)
    nf.notify_warning(f"Error cancel Reservation ID={pk} in Odoo\n{failure.short_info()}")
    if failure.failure == ReservationErrors.error:
        raise self.retry(exc=failure.exc)


@shared_task(bind=True, name='board.register_reservation_in_odoo', retry_kwargs={'max_retries': 2})
def register_reservation_in_odoo(self, hid: int, pk: int, user_id: int = None) -> None:
    result = RegisterReservationInOdoo().execute(hid, pk, user_id=user_id)
    if is_successful(result):
        auto_make_invoice.delay(pk)
        return
    failure = result.failure()
    if failure.failure == ReservationErrors.room_close_reservation:
        # It's normal case but use error just for breaking flow
        return
    Logger.warning(__name__, failure)
    nf.notify_warning(f"Error register Reservation ID={pk} in Odoo\n{failure.short_info()}")
    if failure.failure in (ReservationErrors.error, ReservationErrors.save):
        raise self.retry(exc=failure.exc)


@shared_task(bind=True, name='board.update_reservation_in_odoo', retry_kwargs={'max_retries': 2})
def update_reservation_in_odoo(self, hid: int, pk: int, user_id: int = None) -> None:
    result = UpdateReservationInOdoo().execute(hid, pk, user_id=user_id)
    if is_successful(result):
        auto_make_invoice.delay(pk)
        return
    failure = result.failure()
    if failure.failure == ReservationErrors.room_close_reservation:
        # It's normal case but use error just for breaking flow
        return
    Logger.warning(__name__, failure)
    nf.notify_warning(f"Error update Reservation ID={pk} in Odoo\n{failure.short_info()}")
    if failure.failure == ReservationErrors.error:
        raise self.retry(exc=failure.exc)


@shared_task(bind=True, name='board.update_reservations', retry_kwargs={'max_retries': 2})
def update_reservations(
    self,
    hid: int = None,
    pk: int = None,
    start_date: Union[str, datetime.date] = None,
    end_date: Union[str, datetime.date] = None,
) -> None:
    if start_date is not None and not isinstance(start_date, datetime.date):
        start_date = cf.get_date_or_none(start_date)
    if end_date is not None and not isinstance(end_date, datetime.date):
        end_date = cf.get_date_or_none(end_date)
    result = UpdateReservationCache().execute(house_id=hid, start_date=start_date, end_date=end_date, pk=pk)
    if is_successful(result):
        return
    failure = result.failure()
    Logger.warning(__name__, failure)
    nf.notify_warning(f"Error update reservation cache\n{failure.short_info()}")
    raise self.retry(exc=failure.exc)
