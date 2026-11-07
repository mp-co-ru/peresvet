"""Журнал камеры с теми же ключами ``log``, что у коннектора.

``level``, ``fileName``, ``maxBytes`` и ``backupCount`` задают файл
на машине подхвата. ``sendToPlatform`` — флажок «Лог в платформу»:
те же строки уходят сообщением ``prsConnector.log_line``.
"""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from src.services.video.camera import LOG_BACKUP_COUNT, LOG_MAX_BYTES, redact_rtsp

_Emit = Callable[[str, str, str, int], Awaitable[None]]

_emit: _Emit | None = None
_override_send: dict[str, bool] = {}


def default_file_name(conn_id: str) -> str:
    return f"logs/prs_connector_{conn_id}.log"


def resolve_file_name(file_name: str, conn_id: str) -> str:
    text = (file_name or "").strip()
    if not text:
        return default_file_name(conn_id)
    return text.replace("{id}", conn_id)


def bind(post_message) -> None:
    """Куда слать строку. ``post_message`` — метод сервиса подхвата."""

    async def emit(conn_id: str, level: str, message: str, ts: int) -> None:
        try:
            await post_message(
                mes={
                    "action": "prsConnector.log_line",
                    "data": {
                        "id": conn_id,
                        "level": level,
                        "message": message,
                        "ts": ts,
                    },
                },
                routing_key=f"conn2prs.{conn_id}",
            )
        except Exception:
            return

    global _emit
    _emit = emit


@dataclass
class _Applied:
    level: str
    file_name: str
    max_bytes: int
    backup_count: int
    send: bool


_applied: dict[str, _Applied] = {}


class _PlatformHandler(logging.Handler):
    def __init__(self, conn_id: str) -> None:
        super().__init__(level=logging.DEBUG)
        self.conn_id = conn_id

    def emit(self, record: logging.LogRecord) -> None:
        if _emit is None:
            return
        try:
            message = redact_rtsp(self.format(record))[:8192]
        except Exception:
            return
        if not message:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(_emit(self.conn_id, record.levelname, message, int(record.created)))


def _logger(conn_id: str) -> logging.Logger:
    return logging.getLogger(f"prs_connector_{conn_id}")


def _install(conn_id: str, applied: _Applied) -> None:
    logger = _logger(conn_id)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(applied.level)
    logger.propagate = False
    path = Path(applied.file_name)
    if path.parent and str(path.parent) not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s :: [%(levelname)s] :: %(name)s :: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.handlers.RotatingFileHandler(
        applied.file_name,
        maxBytes=applied.max_bytes,
        backupCount=applied.backup_count,
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    if applied.send:
        platform = _PlatformHandler(conn_id)
        platform.setFormatter(formatter)
        logger.addHandler(platform)
    _applied[conn_id] = applied


def configure(
    conn_id: str,
    *,
    send: bool,
    level: str,
    file_name: str = "",
    max_bytes: int = LOG_MAX_BYTES,
    backup_count: int = LOG_BACKUP_COUNT,
) -> None:
    """Состояние из сохранённой конфигурации коннектора."""
    if conn_id in _override_send and _override_send[conn_id] == bool(send):
        _override_send.pop(conn_id, None)
    if conn_id in _override_send:
        send = _override_send[conn_id]
    _install(conn_id, _Applied(
        level=(level or "INFO").upper(),
        file_name=resolve_file_name(file_name, conn_id),
        max_bytes=max_bytes,
        backup_count=backup_count,
        send=bool(send),
    ))


def command(conn_id: str, send: bool) -> None:
    """Флажок «Лог в платформу», пока узел ещё не записан."""
    current = _applied.get(conn_id)
    _override_send[conn_id] = bool(send)
    if current is None:
        configure(conn_id, send=bool(send), level="INFO")
        _override_send[conn_id] = bool(send)
        return
    _install(conn_id, _Applied(
        level=current.level,
        file_name=current.file_name,
        max_bytes=current.max_bytes,
        backup_count=current.backup_count,
        send=bool(send),
    ))


def clear(conn_id: str) -> None:
    logger = _logger(conn_id)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    _applied.pop(conn_id, None)
    _override_send.pop(conn_id, None)


def note(conn_id: str, level: str, message: str) -> None:
    """Строка сеанса. В файл и в платформу её пускает уже настроенный журнал."""
    text = redact_rtsp(message or "")[:8192]
    if not text or conn_id not in _applied:
        return
    level_name = (level or "INFO").upper()
    _logger(conn_id).log(getattr(logging, level_name, logging.INFO), text)


def reset_for_tests() -> None:
    global _emit
    for conn_id in list(_applied):
        clear(conn_id)
    _emit = None
    _applied.clear()
    _override_send.clear()
