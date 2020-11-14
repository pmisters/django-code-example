import dataclasses
from typing import Callable, ClassVar

from returns.maybe import Nothing
from returns.result import Success

from board.value_objects import ReservationErrors
from common import functions as cf
from common.value_objects import ResultE


class ReservationSelectMixin:
    _error: Callable
    _reservations_repo: ClassVar

    def select_reservation(self, ctx: dataclasses.dataclass) -> ResultE[dataclasses.dataclass]:
        """Select reservation from Repository and check if it is acceptable"""
        pk = cf.get_int_or_none(ctx.pk) or 0
        if pk <= 0:
            return self._error('Missed Reservation ID', ctx, ReservationErrors.missed_reservation)
        try:
            data = self._reservations_repo.get(pk)
        except Exception as err:
            return self._error(
                f"Error select Reservation ID={pk} in House ID={ctx.house.id}", ctx, ReservationErrors.error, exc=err
            )
        if data == Nothing:
            return self._error(
                f"Unknown Reservation ID={pk} in House ID={ctx.house.id}", ctx, ReservationErrors.missed_reservation
            )
        if hasattr(ctx, 'source'):
            ctx.source = data.unwrap()
        else:
            ctx.reservation = data.unwrap()
        return Success(ctx)
