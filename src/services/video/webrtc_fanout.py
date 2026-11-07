"""Один процесс раздачи: кадры H.264 из подхвата уходят всем зрителям.

Кодирует ffmpeg. Этот модуль только передаёт уже собранные кадры
в процесс, который копирует их в RTP каждому PeerConnection.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

import aiohttp

logger = logging.getLogger("video")

_SIGNAL = os.environ.get("VIDEO_WEBRTC_SIGNAL", "127.0.0.1:8190")
_INGEST = os.environ.get("VIDEO_WEBRTC_INGEST", "127.0.0.1:8191")
_PORT = os.environ.get("VIDEO_WEBRTC_PORT", "8189")

_process: asyncio.subprocess.Process | None = None
_start_lock = asyncio.Lock()
_writers: dict[str, "_FrameWriter"] = {}
_missing_logged = False


def fanout_binary() -> str:
    configured = os.environ.get("VIDEO_WEBRTC_BIN", "").strip()
    if configured:
        return configured
    return str(Path(__file__).resolve().parent / "webrtc_fanout" / "prs-webrtc-fanout")


def _binary_ready() -> bool:
    path = fanout_binary()
    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


async def ensure_fanout() -> None:
    """Поднимает процесс раздачи, если бинарь есть."""
    from src.services.video.runtime import VideoRuntimeError

    global _process, _missing_logged
    if not _binary_ready():
        if not _missing_logged:
            _missing_logged = True
            logger.warning("Нет программы раздачи WebRTC: %s", fanout_binary())
        raise VideoRuntimeError("На сервере нет раздачи WebRTC.")
    async with _start_lock:
        if _process is not None and _process.returncode is None:
            return
        _process = await asyncio.create_subprocess_exec(
            fanout_binary(),
            "-port", _PORT,
            "-http", _SIGNAL,
            "-ingest", _INGEST,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        asyncio.create_task(_drain_fanout_log(_process))
    deadline = asyncio.get_running_loop().time() + 5
    while asyncio.get_running_loop().time() < deadline:
        if _process.returncode is not None:
            raise VideoRuntimeError("Раздача WebRTC завершилась при старте.")
        try:
            _reader, writer = await asyncio.open_connection(*_split_host(_SIGNAL))
        except OSError:
            await asyncio.sleep(0.05)
            continue
        writer.close()
        await writer.wait_closed()
        return
    raise VideoRuntimeError("Раздача WebRTC не открыла порт сигналинга.")


async def _drain_fanout_log(process: asyncio.subprocess.Process) -> None:
    if process.stdout is None:
        return
    try:
        while True:
            line = await process.stdout.readline()
            if not line:
                return
            text = line.decode("utf-8", errors="replace").strip()
            if text:
                logger.info("WebRTC: %s", text)
    except asyncio.CancelledError:
        raise


def publish_access_unit(connector_id: str, unit: bytes) -> None:
    """Кладёт кадр в очередь раздачи. Кодирование здесь не происходит."""
    if not unit or not _binary_ready():
        return
    writer = _writers.get(connector_id)
    if writer is None:
        writer = _FrameWriter(connector_id)
        _writers[connector_id] = writer
        try:
            asyncio.get_running_loop().create_task(writer.run())
        except RuntimeError:
            return
    writer.submit(unit)


async def answer_offer(connector_id: str, sdp: str, advertise_host: str) -> dict:
    from src.services.video.runtime import VideoRuntimeError
    from src.services.video.webrtc_sdp import advertise_sdp

    await ensure_fanout()
    payload = {"connectorId": connector_id, "sdp": sdp, "type": "offer"}
    timeout = aiohttp.ClientTimeout(total=10, sock_connect=2)
    session = aiohttp.ClientSession(timeout=timeout)
    try:
        upstream = await session.post(f"http://{_SIGNAL}/offer", json=payload)
        body = await upstream.read()
        status = upstream.status
    except aiohttp.ClientError as ex:
        raise VideoRuntimeError(f"Раздача WebRTC недоступна: {ex}") from ex
    finally:
        await session.close()
    if status != 200:
        raise VideoRuntimeError(body.decode("utf-8", errors="replace")[:300] or "Отказ раздачи WebRTC.")
    try:
        answer = json.loads(body)
    except json.JSONDecodeError as ex:
        raise VideoRuntimeError("Раздача WebRTC вернула не JSON.") from ex
    if not isinstance(answer, dict) or not answer.get("sdp"):
        raise VideoRuntimeError("Раздача WebRTC не вернула SDP.")
    answer["sdp"] = advertise_sdp(str(answer["sdp"]), advertise_host)
    answer["type"] = answer.get("type") or "answer"
    return answer


def _split_host(addr: str) -> tuple[str, int]:
    host, _, port = addr.rpartition(":")
    return host or "127.0.0.1", int(port or "8190")


class _FrameWriter:
    def __init__(self, connector_id: str):
        self.connector_id = connector_id
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=30)

    def submit(self, unit: bytes) -> None:
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            self._queue.put_nowait(unit)
        except asyncio.QueueFull:
            pass

    async def run(self) -> None:
        host, port = _split_host(_INGEST)
        while True:
            try:
                reader, writer = await asyncio.open_connection(host, port)
            except OSError:
                await asyncio.sleep(0.2)
                continue
            try:
                writer.write(f"{self.connector_id}\n".encode())
                while True:
                    unit = await self._queue.get()
                    writer.write(len(unit).to_bytes(4, "big"))
                    writer.write(unit)
                    await writer.drain()
            except (ConnectionError, OSError):
                pass
            finally:
                writer.close()
            await asyncio.sleep(0.2)
