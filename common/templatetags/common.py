import datetime

import pytz
from django.template import Library

register = Library()


@register.filter
def gmt_offset(tzname: str) -> str:
    tz = pytz.timezone(tzname)
    offset = tz.localize(datetime.datetime.now()).strftime("%z")
    return f"GMT {offset[:3]}:{offset[3:]}"
