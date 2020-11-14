from typing import List

import requests

from common import functions as cf
from common.loggers import Logger


def for_develop(message: str) -> None:
    send_bot_message(cf.get_config("TELEGRAM_DEV_USER", ""), message)


def notify_payments(message: str) -> None:
    send_bot_message(cf.get_config("TELEGRAM_PAYMENTS", ""), message)


def notify_fatal(message: str) -> None:
    send_bot_message(cf.get_config("TELEGRAM_FATAL", ""), message)


def notify_warning(message: str) -> None:
    send_bot_message(cf.get_config("TELEGRAM_WARNING", ""), message)


def notify_info(message: str) -> None:
    send_bot_message(cf.get_config("TELEGRAM_INFO", ""), message)


def notify_site_debug(message: str) -> None:
    send_bot_message(cf.get_config("TELEGRAM_LOGGING", ""), message)


def notify_double_booking(message: str) -> None:
    send_bot_message(cf.get_config("TELEGRAM_DOUBLE_BOOKING", ""), message)


def send_bot_message(chat_id: str, message: str, disable_notification: bool = False) -> None:
    url = cf.get_config("TELEGRAM_BOT_URL", "")
    if not url or cf.get_config("DEBUG", False):
        Logger.debug(__name__, f"{chat_id} <-- {message}")
    else:
        _send_bot_message(url, chat_id, message, disable_notification)


def _send_bot_message(url: str, chat_id: str, message: str, disable_notification: bool = False) -> None:
    """Send message via given Telegram BOT url"""
    if url.strip() == "":
        raise AssertionError("Empty Telegram BOT url")
    if chat_id.strip() == "":
        raise AssertionError("Empty Chat/User ID")
    if message.strip() == "":
        return
    chunks = _split_message(message)
    for chunk in chunks:
        data = {
            "chat_id": chat_id,
            "text": chunk,
            "disable_notification": disable_notification,
            "disable_web_page_preview": 1,
        }
        if len(chunk) < 200:
            resp = requests.get(url, params=data)
        else:
            resp = requests.post(url, data)
        if resp.status_code != 200:
            if _mute_telegram_error(resp.content):
                # Don't send next chunks
                return
            Logger.warning(__name__, f"TELEGRAM (CHAT:{chat_id}): [{resp.status_code}] {resp.content!r}")
            continue
        try:
            resp.json()
        except ValueError as err:
            Logger.warning(__name__, f"TELEGRAM (CHAT:{chat_id}): {err}")


def _mute_telegram_error(content: bytes) -> bool:
    if b"[Error]: Bad Request: chat not found" in content:
        return True
    if b"Too Many Requests: retry after" in content:
        return True
    return False


def _split_message(message: str, size: int = 4000) -> List[str]:
    """Split long message for Telegram"""
    if len(message) < size:
        return [message]
    result = []
    value = message
    while len(value) > 0:
        i = size
        if len(value) < i:
            i = len(value)
        part = value[0:i]
        if "\n" in part and len(value[i:]) > 0:
            i = part.rfind("\n") + 1
            part = value[0:i]
        result.append(part)
        value = value[i:]
    return result
