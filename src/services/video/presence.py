"""MQTT-сессия камеры: ClientId равен id коннектора.

Платформа красит кружок в дереве по живой MQTT-сессии на брокере.
Пока сеанс RTSP жив, видеосервер держит такую сессию. Когда сеанс
останавливается, сессия закрывается и кружок гаснет.
Коды качества 100 и 101 при этом не публикуются: камера не запрашивает
конфигурацию коннектора.
"""

from __future__ import annotations

import asyncio
import logging
import os
from urllib.parse import unquote, urlsplit

logger = logging.getLogger("video")

_settings: tuple[str, int, str, str] | None = None
_stops: dict[str, asyncio.Event] = {}
_tasks: dict[str, asyncio.Task] = {}


def configure_presence(amqp_url: str, mqtt_port: int | None = None) -> None:
    parsed = urlsplit(amqp_url or "")
    host = parsed.hostname or "rabbitmq"
    user = unquote(parsed.username or "prs")
    password = unquote(parsed.password or "")
    port = mqtt_port if mqtt_port is not None else int(os.getenv("RABBIT_MQTT_PORT", "1883"))
    global _settings
    _settings = (host, port, user, password)


def mqtt_connect_packet(client_id: str, username: str, password: str, keepalive: int) -> bytes:
    """CONNECT MQTT 3.1.1: чистая сессия, логин и пароль брокера."""
    payload = _mqtt_str(client_id) + _mqtt_str(username) + _mqtt_str(password)
    variable = b"\x00\x04MQTT\x04\xc2" + int(keepalive).to_bytes(2, "big") + payload
    return bytes([0x10]) + _remaining_length(len(variable)) + variable


def _mqtt_str(value: str) -> bytes:
    raw = value.encode("utf-8")
    return len(raw).to_bytes(2, "big") + raw


def _remaining_length(length: int) -> bytes:
    out = bytearray()
    while True:
        digit = length % 128
        length //= 128
        if length:
            digit |= 0x80
        out.append(digit)
        if not length:
            return bytes(out)


def hold_camera_presence(connector_id: str) -> None:
    if _settings is None:
        return
    current = _tasks.get(connector_id)
    if current is not None and not current.done():
        return
    stop = asyncio.Event()
    _stops[connector_id] = stop
    _tasks[connector_id] = asyncio.create_task(_presence_loop(connector_id, stop))


async def drop_camera_presence(connector_id: str) -> None:
    stop = _stops.pop(connector_id, None)
    task = _tasks.pop(connector_id, None)
    if stop is not None:
        stop.set()
    if task is None:
        return
    try:
        await asyncio.wait_for(task, timeout=3)
    except TimeoutError:
        task.cancel()


async def _presence_loop(connector_id: str, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await _one_session(connector_id, stop)
        except asyncio.CancelledError:
            raise
        except Exception as ex:
            logger.warning("Камера %s: MQTT-сессия не открылась: %s", connector_id, ex)
        if stop.is_set():
            return
        try:
            await asyncio.wait_for(stop.wait(), timeout=5)
        except TimeoutError:
            continue


async def _one_session(connector_id: str, stop: asyncio.Event) -> None:
    if _settings is None:
        return
    host, port, user, password = _settings
    reader, writer = await asyncio.open_connection(host, port)
    try:
        writer.write(mqtt_connect_packet(connector_id, user, password, keepalive=60))
        await writer.drain()
        packet_type, body = await _read_packet(reader, timeout=5)
        if packet_type != 0x20 or len(body) < 2 or body[1] != 0:
            raise RuntimeError(f"брокер отклонил CONNECT, код {body[1] if len(body) > 1 else packet_type}")
        logger.info("Камера %s: MQTT-сессия на брокере", connector_id)
        reader_task = asyncio.create_task(_drain_broker(reader, stop))
        try:
            while not stop.is_set() and not reader_task.done():
                try:
                    await asyncio.wait_for(stop.wait(), timeout=20)
                except TimeoutError:
                    writer.write(b"\xc0\x00")
                    await writer.drain()
        finally:
            if not reader_task.done():
                reader_task.cancel()
            try:
                writer.write(b"\xe0\x00")
                await writer.drain()
            except Exception:
                pass
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def _drain_broker(reader: asyncio.StreamReader, stop: asyncio.Event) -> None:
    try:
        while not stop.is_set():
            await _read_packet(reader, timeout=90)
    except asyncio.CancelledError:
        raise
    except Exception:
        return


async def _read_packet(reader: asyncio.StreamReader, timeout: float) -> tuple[int, bytes]:
    header = await asyncio.wait_for(reader.readexactly(1), timeout)
    value = 0
    multiplier = 1
    for _ in range(4):
        digit = (await asyncio.wait_for(reader.readexactly(1), timeout))[0]
        value += (digit & 0x7F) * multiplier
        if not digit & 0x80:
            break
        multiplier *= 128
    else:
        raise RuntimeError("слишком длинный пакет MQTT")
    body = await asyncio.wait_for(reader.readexactly(value), timeout) if value else b""
    return header[0], body
