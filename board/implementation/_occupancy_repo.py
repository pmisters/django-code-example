import datetime
from typing import Dict, List, Optional, Union

from django_redis import get_redis_connection
from redis import Redis

from board.repositories import OccupancyRepo
from common import cache_keys, functions as cf


class OccupancyRepoRedis(OccupancyRepo):
    def set(self, house_id: int, roomtype_id: int, values: Dict[datetime.date, int]) -> None:
        name = cache_keys.occupancy(house_id, roomtype_id)
        self.get_store().hset(name, mapping={self.format_date(x): y for x, y in values.items()})

    def get(
        self, house_id: int, roomtype_id: int, dates: Union[datetime.date, List[datetime.date]],
    ) -> Dict[datetime.date, Optional[int]]:
        if isinstance(dates, datetime.date):
            dates = [dates]
        if not isinstance(dates, list):
            raise AssertionError("Wrong input for OccupancyRepo.get")
        name = cache_keys.occupancy(house_id, roomtype_id)
        result = self.get_store().hmget(name, [self.format_date(x) for x in dates])
        return {x: cf.get_int_or_none(y) for x, y in zip(dates, result)}

    @staticmethod
    def get_store() -> Redis:
        return get_redis_connection("default")

    @staticmethod
    def format_date(value: datetime.date) -> str:
        return value.strftime("%Y-%m-%d")
