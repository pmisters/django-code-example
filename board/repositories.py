import abc
import datetime
from typing import Dict, List, TYPE_CHECKING, Tuple, Union

from returns.maybe import Maybe

if TYPE_CHECKING:
    from board.entities import Reservation
    from board.value_objects import CachedReservation
    from channels.entities import Connection


class OccupancyRepo(abc.ABC):
    @abc.abstractmethod
    def set(self, house_id: int, roomtype_id: int, values: Dict[datetime.date, int]) -> None:
        pass

    @abc.abstractmethod
    def get(
        self, house_id: int, roomtype_id: int, dates: Union[datetime.date, List[datetime.date]],
    ) -> Dict[datetime.date, int]:
        pass


class ReservationsRepo(abc.ABC):
    @abc.abstractmethod
    def accept(self, pk: int, price_ids: List[int] = None) -> Maybe['Reservation']:
        pass

    @abc.abstractmethod
    def get(self, pk: int, with_deleted_rooms: bool = False) -> Maybe['Reservation']:
        pass

    @abc.abstractmethod
    def is_room_busy(
        self, room_id: int, start_date: datetime.date, end_date: datetime.date, exclude_rooms: List[int] = None
    ) -> bool:
        pass

    @abc.abstractmethod
    def save(
        self, reservation: 'Reservation', with_accepted_prices: bool = False
    ) -> Tuple[Maybe['Reservation'], bool]:
        pass

    @abc.abstractmethod
    def select(
        self,
        connection: 'Connection' = None,
        house_id: int = None,
        channel_ids: List[str] = None,
        start_date: datetime.date = None,
        end_date: datetime.date = None,
        pks: List[int] = None,
    ) -> List['Reservation']:
        pass

    @abc.abstractmethod
    def select_busy_days(
        self, house_id: int, roomtype_ids: List[int], start_date: datetime.date = None, end_date: datetime.date = None
    ) -> Dict[int, Dict[datetime.date, int]]:
        pass


class ReservationsCacheRepo(abc.ABC):
    @abc.abstractmethod
    def search(self, house_id: int) -> List['CachedReservation']:
        pass

    @abc.abstractmethod
    def get(self, house_id: int, pk: str) -> Maybe['CachedReservation']:
        pass

    @abc.abstractmethod
    def save(self, house_id: int, reservation: 'CachedReservation') -> bool:
        pass

    @abc.abstractmethod
    def delete(self, house_id: int, reservation_id: int) -> None:
        pass
