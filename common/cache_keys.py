from typing import Union

from contrib.chmanager.models import Booking, Hotel
from members.models import Company


def _key(*args) -> str:
    return ":".join([str(x) for x in args])


def occupancy(house_id: int, roomtype_id: int) -> str:
    return _key("OCP", house_id, roomtype_id)


def reservation(house_id: int, reservation_id: Union[int, str]) -> str:
    return _key("RES", house_id, reservation_id)


# OLD


def key_for_update_availability(pk: int, channel: str) -> str:
    return ":".join(["AVAIL", "UPD", str(pk), channel])


def key_for_unsubscribe(email: str) -> str:
    email = email or ""
    return ":".join(["UNSUBSCR", email.strip().lower()])


def key_for_delete_company(pk: int) -> str:
    return ":".join(["DEL", "COMPANY", str(int)])


def get_double_booking_error_key(booking: Booking) -> str:
    return ":".join(["CH", "ERR", str(booking.channel_id)])


def ota_update_error_key(hotel: Hotel, channel: str) -> str:
    return ":".join(["CH", "UPD", "ERR", str(hotel.id), channel])


def ota_update_flag_key(company: Company) -> str:
    return ":".join(["UPOTA", str(company.id)])


def ota_update_error_flag_key(company: Company) -> str:
    return ":".join(["CH", "UPD", "ERR", "FLAG", str(company.id)])
