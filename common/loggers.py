import datetime
import sys
from typing import Any, Dict, Optional

from loguru import logger

from common import functions as cf
from effective_tours.constants import Channels


class Logger:
    configured_handlers = None

    @staticmethod
    def configure() -> None:
        project_root = cf.get_config("PROJECT_ROOT")
        log_dir = project_root.joinpath("logs")

        # Reset all configuration
        logger.remove(None)

        # Global Console
        logger.add(
            sys.stdout, level="DEBUG", catch=True, backtrace=True, diagnose=False, format=Logger.console_format
        )

        # ODOO API
        logger.add(
            log_dir.joinpath("odoo.log"),
            level="DEBUG",
            format=Logger.odoo_file_format,
            filter=lambda x: "odoo" in x["extra"].get("name", ""),
            catch=True,
            diagnose=False,
            rotation=datetime.timedelta(days=1),
        )

        # OTA Channels API
        logger.add(
            log_dir.joinpath("channels.log"),
            level="DEBUG",
            format=Logger.channel_file_format,
            filter=lambda x: "channels" in x["extra"].get("name", ""),
            catch=True,
            diagnose=False,
            rotation=datetime.timedelta(days=1),
        )

        # Errors & Warnings
        logger.add(
            log_dir.joinpath("errors.log"),
            level="WARNING",
            format=Logger.global_file_format,
            catch=True,
            diagnose=False,
            rotation=datetime.timedelta(days=1),
        )

    @staticmethod
    def channel_file_format(record):
        fmt = ["{level} {time:YYYY-MM-DD HH:mm:ss,SSS} "]
        if isinstance(record["extra"].get("channel"), Channels):
            channel = record["extra"]["channel"].name.lower()
            fmt.append(f"[{channel}]")
        if cf.get_int_or_none(record["extra"].get("house")) is not None:
            house_id = cf.get_int_or_none(record["extra"]["house"])
            fmt.append(f"[H:{house_id}]")
        if (record["extra"].get("request_id") or "").strip() != "":
            fmt.append(f'[ParentRID:{record["extra"]["request_id"]}]')
        fmt.append(" {message} \n")

        format_string = "".join(fmt)
        if record.get("exception") is not None:
            format_string += "{exception} \n"
        return format_string

    @staticmethod
    def console_format(record):
        record["extra"].setdefault("name", "")
        fmt = " | ".join(
            [
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green>",
                "<level>{level: <8}</level>",
                "<cyan>{extra[name]: <10}</cyan>",
                "<level>{message}</level>\n",
            ]
        )
        if record.get("exception") is not None:
            fmt += "{exception}\n"
        return fmt

    @staticmethod
    def global_file_format(record):
        record["extra"].setdefault("name", "")
        fmt = " | ".join(["{time:YYYY-MM-DD HH:mm:ss.SSS}", "{level: <8}", "{extra[name]: <10}", "{message} \n"])
        if record.get("exception") is not None:
            fmt += "{exception} \n"
        return fmt

    @staticmethod
    def odoo_file_format(record):
        record["extra"].setdefault("name", "")
        fmt = " | ".join(["{time:YYYY-MM-DD HH:mm:ss.SSS}", "{level: <8}", "{extra[name]: <10}", "{message} \n"])
        if record.get("exception") is not None:
            fmt += "{exception} \n"
        return fmt

    @staticmethod
    def get_house_log_name(routing: Dict[str, Any]) -> str:
        if not isinstance(routing.get("channel"), Channels):
            return ""
        channel = routing["channel"].name.lower()
        house_id = cf.get_int_or_none(routing.get("house"))
        if house_id is None:
            return ""
        return f"ch-{house_id}-{channel}"

    @staticmethod
    def apply_routing(routing: Dict[str, Any] = None) -> Optional[str]:
        if routing is None or not routing:
            return None
        name = Logger.get_house_log_name(routing)
        if name == "":
            return None
        if Logger.configured_handlers is None:
            Logger.configured_handlers = []
        if name not in Logger.configured_handlers:
            project_root = cf.get_config("PROJECT_ROOT")
            logger.add(
                project_root.joinpath("logs").joinpath(f"{name}.log"),
                level="DEBUG",
                format=Logger.channel_file_format,
                filter=lambda x: x["extra"].get("name", "") == name,
                catch=True,
                diagnose=False,
                rotation=datetime.timedelta(days=1),
            )
            Logger.configured_handlers.append(name)
        return name

    # Helper functions

    @staticmethod
    def debug(name: str, msg: str, *args, routing: Dict[str, Any] = None, **kwargs) -> None:
        routing = routing or {}
        name = Logger.apply_routing(routing) or name
        logger.bind(name=name, **routing).debug(msg, *args, **kwargs)

    @staticmethod
    def info(name: str, msg: str, *args, routing: Dict[str, Any] = None, **kwargs) -> None:
        routing = routing or {}
        name = Logger.apply_routing(routing) or name
        logger.bind(name=name, **routing).info(msg, *args, **kwargs)

    @staticmethod
    def success(name: str, msg: str, *args, routing: Dict[str, Any] = None, **kwargs) -> None:
        routing = routing or {}
        name = Logger.apply_routing(routing) or name
        logger.bind(name=name, **routing).success(msg, *args, **kwargs)

    @staticmethod
    def warning(name: str, msg: str, *args, routing: Dict[str, Any] = None, **kwargs) -> None:
        routing = routing or {}
        name = Logger.apply_routing(routing) or name
        logger.bind(name=name, **routing).warning(msg, *args, **kwargs)

    @staticmethod
    def error(name: str, msg: str, *args, routing: Dict[str, Any] = None, **kwargs) -> None:
        routing = routing or {}
        name = Logger.apply_routing(routing) or name
        logger.bind(name=name, **routing).error(msg, *args, **kwargs)

    @staticmethod
    def fatal(name: str, msg: str, *args, routing: Dict[str, Any] = None, **kwargs) -> None:
        routing = routing or {}
        name = Logger.apply_routing(routing) or name
        logger.bind(name=name, **routing).exception(msg, *args, **kwargs)
