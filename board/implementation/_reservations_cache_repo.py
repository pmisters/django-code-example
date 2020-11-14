from typing import List

from django_redis import get_redis_connection
from redis import Redis
from returns.maybe import Maybe, Nothing, Some
from pydantic import ValidationError

from board.repositories import ReservationsCacheRepo
from board.value_objects import CachedReservation
from common import cache_keys
from common.loggers import Logger


class ReservationsCacheRepoRedis(ReservationsCacheRepo):
    def search(self, house_id: int) -> List[CachedReservation]:
        result = []
        store = self.get_store()
        for key in store.keys(cache_keys.reservation(house_id, "*")):
            try:
                data = store.get(key).decode("utf8")
                result.append(CachedReservation.parse_raw(data))
            except ValidationError as err:
                Logger.warning(__name__, f"Error decode Cache Reservation [{key}] : {err}")
        return result

    def get(self, house_id: int, pk: str) -> Maybe[CachedReservation]:
        key = cache_keys.reservation(house_id, pk)
        data = self.get_store().get(key)
        if data is None or not data:
            return Nothing
        try:
            return Some(CachedReservation.parse_raw(data))
        except ValidationError as err:
            Logger.warning(__name__, f"Error decode Cache Reservation [{key}] : {err}")
        return Nothing

    def save(self, house_id: int, reservation: CachedReservation) -> bool:
        key = cache_keys.reservation(house_id, reservation.pk)
        return self.get_store().set(key, reservation.json())

    def delete(self, house_id: int, reservation_id: int) -> None:
        pattern = cache_keys.reservation(house_id, f"{reservation_id}-*")
        store = self.get_store()
        for key in store.keys(pattern):
            store.delete(key)

    @staticmethod
    def get_store() -> Redis:
        return get_redis_connection("default")
