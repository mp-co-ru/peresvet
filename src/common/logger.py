#!/usr/bin/env python
# -*- coding: UTF-8 -*-

# Модуль содержит класс журнала

import logging
import logging.config
import os
import sys
import json
import threading
from collections import deque
from datetime import datetime
from typing import Any

from loguru import logger


class PrsLogBuffer:
    """Общий in-memory буфер последних логов платформы для UI."""

    _maxlen = int(os.getenv("PRS_LOG_BUFFER_MAX", "5000"))
    _entries: deque[dict[str, Any]] = deque(maxlen=_maxlen)
    _clear_after_seq_by_service: dict[str, int] = {}
    _seq = 0
    _lock = threading.RLock()

    @classmethod
    def _service_from_message(cls, message: str) -> str:
        for separator in (" ::", ":"):
            if separator in message:
                service = message.split(separator, 1)[0].strip()
                if service:
                    return service
        return ""

    @classmethod
    def append_from_record(cls, record: dict[str, Any]) -> None:
        message = str(record.get("message", ""))
        extra = record.get("extra") or {}
        service = str(extra.get("service") or cls._service_from_message(message) or "")
        when = record.get("time")
        if hasattr(when, "isoformat"):
            ts = when.isoformat()
        else:
            ts = datetime.now().astimezone().isoformat()
        entry = {
            "ts": ts,
            "level": getattr(record.get("level"), "name", str(record.get("level", ""))),
            "service": service,
            "message": message,
            "line": f"{ts} [{getattr(record.get('level'), 'name', '')}] {message}",
        }
        with cls._lock:
            cls._seq += 1
            entry["seq"] = cls._seq
            cls._entries.append(entry)

    @classmethod
    def loguru_sink(cls, message) -> None:
        cls.append_from_record(message.record)

    @classmethod
    def tail(cls, services: list[str] | None = None, limit: int = 400) -> list[dict[str, Any]]:
        service_set = {service.strip() for service in services or [] if service and service.strip()}
        limit = max(1, min(int(limit or 400), 2000))
        with cls._lock:
            entries = list(cls._entries)
            clear_after = dict(cls._clear_after_seq_by_service)
        if service_set:
            entries = [
                entry
                for entry in entries
                if any(
                    cls._matches_service(entry, service)
                    and int(entry.get("seq") or 0) > clear_after.get(service, 0)
                    for service in service_set
                )
            ]
        else:
            entries = [
                entry
                for entry in entries
                if int(entry.get("seq") or 0) > clear_after.get(str(entry.get("service") or ""), 0)
            ]
        return entries[-limit:]

    @classmethod
    def clear(cls, services: list[str] | None = None) -> int:
        service_set = {service.strip() for service in services or [] if service and service.strip()}
        with cls._lock:
            if not service_set:
                cleared = len(cls._entries)
                cls._entries.clear()
                cls._clear_after_seq_by_service.clear()
                return cleared

            clear_after_seq = cls._seq
            keep = deque(maxlen=cls._maxlen)
            cleared = 0
            for service in service_set:
                cls._clear_after_seq_by_service[service] = clear_after_seq
            for entry in cls._entries:
                if any(cls._matches_service(entry, service) for service in service_set):
                    cleared += 1
                    continue
                keep.append(entry)
            cls._entries = keep
            return cleared

    @classmethod
    def _matches_service(cls, entry: dict[str, Any], service: str) -> bool:
        message = str(entry.get("message", ""))
        return entry.get("service") == service or message.startswith((f"{service} ::", f"{service}:"))

class InterceptHandler(logging.Handler):
    loglevel_mapping = {
        50: 'CRITICAL',
        40: 'ERROR',
        30: 'WARNING',
        20: 'INFO',
        10: 'DEBUG',
        0: 'NOTSET',
    }

    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except AttributeError:
            level = self.loglevel_mapping[record.levelno]

        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        log = logger.bind(request_id='app')
        log.opt(
            depth=depth,
            exception=record.exc_info
        ).log(level,record.getMessage())

class PrsLogger:
    """Класс журнала.
    Для настройки используются 4 переменных окружения:

    **LOG_LEVEL** - уровень журналирования
    (CRITICAL, ERROR, WARNING, INFO, DEBUG);

    **LOG_FILE_NAME** - имя файла журнала;

    **LOG_RETENTION**

    **LOG_ROTATION**

    Журнал создаётся функцией ``make_logger``.
    """

    @classmethod
    def make_logger(
        cls,
        level: str = "CRITICAL",
        file_name: str = "log/peresvet.log",
        retention: str = "1 months",
        rotation: str = "20 days",
        service_name: str = ""
    ):
        """Функция создаёт новый журнал.

        Returns:
            Настроенный экземпляр журнала.
        """
        if level in ("DEBUG", "ERROR"):
            fmt = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> <level>{level: <8}</level> : {name}.{function}.{line} :: <level>{message}</level>"
        else:
            fmt = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> <level>{level: <8}</level> :: <level>{message}</level>"

        return cls.customize_logging(
            file_name,
            level=level,
            retention=retention,
            rotation=rotation,
            format=fmt,
            service_name=service_name
        )

    @classmethod
    def customize_logging(
            cls, filepath: str, level: str, rotation: str, retention: str,
            format: str, service_name: str = ""
    ):

        logger.remove()
        logger.add(
            sys.stdout,
            enqueue=True,
            colorize=True,
            backtrace=True,
            level=level.upper(),
            format=format
        )
        logger.add(
            str(filepath),
            rotation=rotation,
            retention=retention,
            enqueue=True,
            backtrace=True,
            level=level.upper(),
            format=format
        )
        logger.add(
            PrsLogBuffer.loguru_sink,
            enqueue=False,
            level=level.upper(),
            format="{message}",
            colorize=False,
            backtrace=False,
            diagnose=False,
        )
        logging.basicConfig(handlers=[InterceptHandler()], level=0)
        logging.getLogger("uvicorn.access").handlers = [InterceptHandler()]
        for _log in ['uvicorn',
                     'uvicorn.error',
                     'fastapi'
                     ]:
            _logger = logging.getLogger(_log)
            _logger.handlers = [InterceptHandler()]

        return logger.bind(request_id=None, method=None, service=service_name)


    @classmethod
    def load_logging_config(cls, config_path):
        config = None
        with open(config_path, encoding='utf-8') as config_file:
            config = json.load(config_file)
        return config
