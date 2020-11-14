import datetime
import io
import os
import time
from decimal import Decimal, InvalidOperation
from email.mime.image import MIMEImage
from typing import Any, List, Optional, Tuple

from dateutil import parser
from django.conf import settings
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.utils.crypto import get_random_string
from returns.maybe import Maybe, Nothing, Some


def get_config(key: str, default: Any = None) -> Any:
    """Get settings from django.conf if exists, return default otherwise"""
    return getattr(settings, key, default)


def diff_list(a, b):
    b = set(b)
    return [x for x in a if x not in b]


def get_int_or_none(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_decimal_or_none(value: Any) -> Optional[Decimal]:
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return None


def get_datetime_or_none(value: Any) -> Optional[datetime.datetime]:
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime.combine(value, datetime.time(0))
    try:
        return parser.parse(value)
    except (TypeError, ValueError, AttributeError):
        return None


def get_date_or_none(value: Any, **kwargs) -> Optional[datetime.date]:
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, datetime.datetime):
        return value.date()
    try:
        return parser.parse(value, **kwargs).date()
    except (TypeError, ValueError, AttributeError):
        return None


def get_time_or_none(value: Any) -> Optional[datetime.time]:
    if isinstance(value, datetime.time):
        return value
    if isinstance(value, datetime.datetime):
        return value.time()
    try:
        return parser.parse(value).time()
    except (TypeError, ValueError, AttributeError):
        return None


def get_language_or_default(value: Optional[int]) -> int:
    return value if value is not None else get_config("LANGUAGE_ID", 0)


def xml_to_string(data):
    f = io.BytesIO()
    data.write(f)
    return f.getvalue().decode("utf8")


def chunks(data, n):
    """Yield successive n-sized chunks from data."""
    for i in range(0, len(data), n):
        yield data[i : i + n]


def get_dump_filename(name: str, dump_date: datetime.datetime = None) -> str:
    PROJECT_ROOT = get_config("PROJECT_ROOT")
    dirname = PROJECT_ROOT.joinpath("logs", "archive")
    if not os.path.exists(dirname):
        os.makedirs(dirname)
    if dump_date is None or not isinstance(dump_date, datetime.datetime):
        dump_date = datetime.datetime.now()
    dt = dump_date.strftime("%Y-%m-%d")
    return f"{dirname}/{name}-{dt}.yml"


def make_all_elems_string(data):
    if isinstance(data, list):
        for k, v in enumerate(data):
            data[k] = make_all_elems_string(v)
    elif isinstance(data, dict):
        for k, v in data.items():
            data[k] = make_all_elems_string(v)
    else:
        data = str(data)
    return data


def round_price(amount: Decimal, precision: Decimal = None) -> Decimal:
    """Round amount with given precision"""
    if precision is None or not isinstance(precision, Decimal):
        precision = Decimal("0.01")
    return Decimal(amount).quantize(precision)


def generate_code(length: int = 10, allowed_chars: str = None) -> str:
    """
    Generates a unique random code with the given length and given
    allowed_chars. Note that the default value of allowed_chars does not
    have "I" or "O" or letters and digits that look similar -- just to
    avoid confusion.

    """
    if allowed_chars is None:
        allowed_chars = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return get_random_string(length, allowed_chars)


def send_email_with_logo(subject, text, to_address, from_address, html=None):
    if html is not None:
        msg = EmailMultiAlternatives(subject, text, from_address, to_address)
        msg.attach_alternative(html, "text/html")
    else:
        msg = EmailMessage(subject, text, from_address, to_address)
    msg.reply_to = [from_address]
    if html is not None and html.find("470d34c254ed$74sfr210$0400a8c0@stal") > 0:
        image = get_config("EMAIL_LOGO", None)
        if image is not None and os.path.exists(image):
            img = MIMEImage(open(image, "rb").read())
            img.add_header("Content-ID", "<470d34c254ed$74sfr210$0400a8c0@stal>")
            img.add_header("Content-Disposition", "inline")
            msg.attach(img)
    try:
        msg.send(fail_silently=False)
    except Exception:
        time.sleep(1)
        msg.send(fail_silently=False)
    return True


def normalize_email(email: str) -> str:
    """
    Normalize the address by lowercasing the domain part of the email address

    """
    email = email or ""
    try:
        email_name, email_domain = email.strip().rsplit("@", 1)
    except ValueError:
        pass
    else:
        email = "@".join([email_name, email_domain.lower()])
    return email


def get_days_for_period(
    start_date: datetime.date, end_date: datetime.date, exclude: bool = False
) -> List[datetime.date]:
    if exclude:
        end_date -= datetime.timedelta(days=1)
    result = []
    day = start_date
    while day <= end_date:
        result.append(day)
        day += datetime.timedelta(days=1)
    return result


def safe_dump(data: Any) -> str:
    if isinstance(data, dict):
        _data = dict(data)
        for key, __ in _data.items():
            if key.lower() == "password":
                _data[key] = "xxx"
        result = f"{_data!r}"
    else:
        result = f"{data!r}"
    if get_config("ODOO_PASSWORD", "") != "":
        result = result.replace(get_config("ODOO_PASSWORD", ""), "xxx")
    return result


def truncate_obj(value, length: int = 200) -> str:
    text = repr(value)
    if len(text) > length:
        return text[: length - 15] + " ... " + text[-10:]
    return text


def parse_period(period: str) -> Maybe[Tuple[datetime.date, datetime.date]]:
    daterange = period.strip().split("-")
    if not daterange or len(daterange) != 2:
        return Nothing
    start_date = get_date_or_none(daterange[0].strip(), dayfirst=True)
    if start_date is None:
        return Nothing
    end_date = get_date_or_none(daterange[1].strip(), dayfirst=True)
    if end_date is None:
        return Nothing
    if start_date > end_date:
        return Nothing
    return Some((start_date, end_date))
