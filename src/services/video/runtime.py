"""Один процесс ffmpeg на камеру.

Архив — копия потока камеры, если хранилище не задало размер или частоту.
Живой WebRTC берёт один H.264 из этого же процесса. Распознавание читает
редкий JPEG ``preview.jpg``. Второй сеанс RTSP для кадра не открывается.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import time
from dataclasses import replace
from pathlib import Path

from src.services.video.camera import (
    CameraConfig,
    ffmpeg_bin,
    redact_rtsp,
    segment_seconds,
    session_ffmpeg_args,
)
from src.services.video.platform_log import note as note_platform_log
from src.services.video.presence import drop_camera_presence, hold_camera_presence

logger = logging.getLogger("video")

_JPEG_START = b"\xff\xd8"
_JPEG_END = b"\xff\xd9"


def pop_jpegs(buffer: bytearray, chunk: bytes) -> list[bytes]:
    """Достаёт целые JPEG из потока image2pipe. Неполный хвост остаётся в buffer."""
    buffer.extend(chunk)
    frames: list[bytes] = []
    while True:
        start = buffer.find(_JPEG_START)
        if start < 0:
            if len(buffer) > 1:
                del buffer[:-1]
            break
        if start:
            del buffer[:start]
        end = buffer.find(_JPEG_END, 2)
        if end < 0:
            break
        frames.append(bytes(buffer[: end + 2]))
        del buffer[: end + 2]
    return frames


def mjpeg_part(jpeg: bytes) -> bytes:
    """Один кадр в том виде, который браузер читает из multipart/x-mixed-replace."""
    header = (
        b"--ffmpeg\r\nContent-Type: image/jpeg\r\nContent-Length: "
        + str(len(jpeg)).encode("ascii")
        + b"\r\n\r\n"
    )
    return header + jpeg + b"\r\n"


class VideoRuntimeError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def prune_archive(directory: Path, *, keep_seconds: int, now_sec: int | None = None) -> None:
    if not directory.is_dir():
        return
    now_sec = int(time.time()) if now_sec is None else now_sec
    cutoff = now_sec - keep_seconds
    for path in directory.glob("*.ts"):
        try:
            start_sec = int(path.stem)
        except ValueError:
            continue
        if start_sec < cutoff:
            path.unlink(missing_ok=True)


class CameraSession:
    def __init__(self, connector_id: str, camera: CameraConfig, directory: Path):
        self.connector_id = connector_id
        self.camera = camera
        self.directory = directory
        self.subscribers: list[asyncio.Queue] = []
        self.audio_subscribers: list[asyncio.Queue] = []
        self.ready = asyncio.Event()
        self.latest_jpeg: bytes | None = None
        self._latest_jpeg_at = 0.0
        self._jpeg_buffer = bytearray()
        self._h264_buffer = bytearray()
        self._proc: asyncio.subprocess.Process | None = None
        self._pump_task: asyncio.Task | None = None
        self._audio_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._stderr_lines: list[str] = []
        self._want_audio = connector_id not in _silent_cameras
        self._stopped = False
        self._restarting = False
        self._prune_task: asyncio.Task | None = None

    @property
    def url(self) -> str:
        return self.camera.rtsp_url

    def alive(self) -> bool:
        if self._stopped:
            return False
        if self._restarting:
            return True
        return self._proc is not None and self._proc.returncode is None

    async def start(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        prune_archive(self.directory, keep_seconds=int(self.camera.retention_hours * 3600))
        logger.info(
            "Камера %s: RTSP %s",
            self.connector_id,
            self.camera.log_target,
        )
        note_platform_log(self.connector_id, "INFO", f"RTSP {self.camera.log_target}")
        await self._open_process()
        self._prune_task = asyncio.create_task(self._prune_expired())
        self._pump_task = asyncio.create_task(self._pump())
        try:
            await asyncio.wait_for(self.ready.wait(), timeout=20)
        except TimeoutError as ex:
            await self.stop()
            raise VideoRuntimeError(
                f"Камера {self.camera.log_target} не прислала кадр за 20 с."
            ) from ex
        hold_camera_presence(self.connector_id)

    async def _prune_expired(self) -> None:
        """Удаляет фрагменты старше уже применённого срока. Настройки не перечитывает."""
        while not self._stopped:
            try:
                await asyncio.sleep(20)
            except asyncio.CancelledError:
                return
            if self._stopped:
                return
            prune_archive(self.directory, keep_seconds=int(self.camera.retention_hours * 3600))

    async def stop(self) -> None:
        self._stopped = True
        await drop_camera_presence(self.connector_id)
        proc = self._proc
        self._proc = None
        if proc is not None and proc.returncode is None:
            proc.kill()
            try:
                await proc.wait()
            except ProcessLookupError:
                pass
        for task in (self._prune_task, self._pump_task, self._audio_task, self._stderr_task):
            if task is not None and not task.done():
                task.cancel()
        for queue in list(self.subscribers):
            queue.put_nowait(None)
        self.subscribers.clear()
        self._end_audio()

    def fresh_jpeg(self, max_age: float = 3.0) -> bytes | None:
        """Последний кадр распознавания, если он не старше max_age секунд."""
        path = self.directory / "preview.jpg"
        try:
            if time.time() - path.stat().st_mtime <= max_age:
                data = path.read_bytes()
                if data.startswith(b"\xff\xd8"):
                    return data
        except OSError:
            pass
        jpeg = self.latest_jpeg
        if not jpeg:
            return None
        if time.monotonic() - self._latest_jpeg_at > max_age:
            return None
        return jpeg

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=8)
        self.subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        if queue in self.subscribers:
            self.subscribers.remove(queue)

    def subscribe_audio(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=32)
        if not self._want_audio:
            queue.put_nowait(None)
        else:
            self.audio_subscribers.append(queue)
        return queue

    def unsubscribe_audio(self, queue: asyncio.Queue) -> None:
        if queue in self.audio_subscribers:
            self.audio_subscribers.remove(queue)

    def _end_audio(self) -> None:
        for queue in list(self.audio_subscribers):
            queue.put_nowait(None)
        self.audio_subscribers.clear()

    def _broadcast(self, chunk: bytes) -> None:
        stale: list[asyncio.Queue] = []
        for queue in list(self.subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(chunk)
            except asyncio.QueueFull:
                stale.append(queue)
        for queue in stale:
            self.unsubscribe(queue)

    async def _open_process(self) -> None:
        if self._audio_task is not None and not self._audio_task.done():
            self._audio_task.cancel()
        audio_server = None
        audio_target = None
        if self._want_audio:
            audio_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            audio_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            audio_server.bind(("127.0.0.1", 0))
            audio_server.listen(1)
            audio_server.setblocking(False)
            port = audio_server.getsockname()[1]
            audio_target = f"tcp://127.0.0.1:{port}"
        args = session_ffmpeg_args(
            self.camera,
            self.directory,
            segment_seconds(),
            ffmpeg_bin(),
            audio_target=audio_target,
        )
        self._jpeg_buffer.clear()
        self._h264_buffer.clear()
        self._proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        if audio_server is not None:
            self._audio_task = asyncio.create_task(self._read_audio(audio_server))
        if self._stderr_task is not None and not self._stderr_task.done():
            self._stderr_task.cancel()
        self._stderr_lines = []
        self._stderr_task = asyncio.create_task(self._drain_stderr())

    async def _respawn(self) -> bool:
        self._restarting = True
        try:
            old = self._proc
            self._proc = None
            if old is not None and old.returncode is None:
                old.kill()
                try:
                    await old.wait()
                except ProcessLookupError:
                    pass
            if self._stderr_says_no_audio():
                self._want_audio = False
                _silent_cameras.add(self.connector_id)
                self._end_audio()
                logger.info(
                    "Камера %s: в RTSP нет звука, сеанс только с картинкой",
                    self.connector_id,
                )
                note_platform_log(
                    self.connector_id, "INFO", "В RTSP нет звука, сеанс только с картинкой.",
                )
            logger.warning("Камера %s: поток прервался, перезапуск", self.connector_id)
            note_platform_log(self.connector_id, "WARNING", "Поток прервался, перезапуск.")
            await asyncio.sleep(1)
            if self._stopped:
                return False
            await self._open_process()
            return True
        except Exception as ex:
            logger.warning(
                "Камера %s не перезапустилась: %s",
                self.camera.log_target,
                redact_rtsp(str(ex)),
            )
            note_platform_log(
                self.connector_id,
                "WARNING",
                f"Сеанс не перезапустился: {redact_rtsp(str(ex))}",
            )
            return False
        finally:
            self._restarting = False

    async def _pump(self) -> None:
        try:
            while not self._stopped:
                proc = self._proc
                if proc is None or proc.stdout is None:
                    break
                while not self._stopped:
                    chunk = await proc.stdout.read(65536)
                    if not chunk:
                        break
                    from src.services.video.annexb import pop_access_units
                    from src.services.video.webrtc_fanout import publish_access_unit

                    for unit in pop_access_units(self._h264_buffer, chunk):
                        self.ready.set()
                        publish_access_unit(self.connector_id, unit)
                if self._stopped:
                    break
                await asyncio.sleep(0.1)
                if not await self._respawn():
                    break
        except asyncio.CancelledError:
            raise
        finally:
            for queue in list(self.subscribers):
                queue.put_nowait(None)
            if not self._stopped:
                await drop_camera_presence(self.connector_id)

    async def _drain_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        try:
            while not self._stopped:
                line = await proc.stderr.readline()
                if not line:
                    break
                text = redact_rtsp(line.decode("utf-8", errors="replace")).strip()
                if text:
                    self._stderr_lines.append(text)
                    logger.warning("Камера %s: %s", self.connector_id, text)
        except asyncio.CancelledError:
            raise

    def _stderr_says_no_audio(self) -> bool:
        if not self._want_audio:
            return False
        text = "\n".join(self._stderr_lines)
        return (
            "does not contain any stream" in text
            or "matches no streams" in text
        )

    async def _read_audio(self, server: socket.socket) -> None:
        """Читает звук всегда, даже без слушателей: иначе ffmpeg заполнит канал и встанет картинка."""
        loop = asyncio.get_running_loop()
        try:
            conn, _ = await loop.sock_accept(server)
        except asyncio.CancelledError:
            server.close()
            raise
        server.close()
        conn.setblocking(False)
        try:
            while not self._stopped:
                try:
                    chunk = await loop.sock_recv(conn, 4096)
                except (ConnectionError, OSError):
                    break
                if not chunk:
                    break
                self._broadcast_audio(chunk)
        except asyncio.CancelledError:
            raise
        finally:
            conn.close()

    def _broadcast_audio(self, chunk: bytes) -> None:
        for queue in list(self.audio_subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(chunk)
            except asyncio.QueueFull:
                self.unsubscribe_audio(queue)


_sessions: dict[str, CameraSession] = {}
_locks: dict[str, asyncio.Lock] = {}
_opening: set[str] = set()
_pending: dict[str, tuple[CameraConfig, Path]] = {}
# Камеры без звука. Новый сеанс не повторяет попытку mp3: она рвёт ffmpeg.
_silent_cameras: set[str] = set()


def _lock_for(connector_id: str) -> asyncio.Lock:
    lock = _locks.get(connector_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[connector_id] = lock
    return lock


def _same_dir(left: Path, right: Path) -> bool:
    if left == right:
        return True
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return False


def _size_fits(current: int | float | None, incoming: int | float | None) -> bool:
    """Запрос без размера не сбрасывает уже открытый сеанс с размером."""
    return incoming is None or current == incoming


def _same_capture(current: CameraSession, camera: CameraConfig, directory: Path) -> bool:
    """Тот же RTSP и та же картинка архива. Срок хранения сюда не входит."""
    stored = current.camera
    return (
        current.url == camera.rtsp_url
        and stored.transport == camera.transport
        and _same_dir(current.directory, directory)
        and _size_fits(stored.archive_width, camera.archive_width)
        and _size_fits(stored.archive_fps, camera.archive_fps)
    )


def _restart_reason(current: CameraSession, camera: CameraConfig, directory: Path) -> str:
    if not current.alive():
        return "сеанс не жив"
    stored = current.camera
    parts: list[str] = []
    if current.url != camera.rtsp_url:
        parts.append("адрес")
    if stored.transport != camera.transport:
        parts.append(f"транспорт {stored.transport} -> {camera.transport}")
    if not _same_dir(current.directory, directory):
        parts.append("каталог")
    if not _size_fits(stored.archive_width, camera.archive_width):
        parts.append(f"ширина {stored.archive_width} -> {camera.archive_width}")
    if not _size_fits(stored.archive_fps, camera.archive_fps):
        parts.append(f"частота {stored.archive_fps} -> {camera.archive_fps}")
    return ", ".join(parts) or "конфигурация"


async def get_session(connector_id: str, camera: CameraConfig, directory: Path | None = None) -> CameraSession:
    directory = directory or camera.segment_dir(connector_id)
    async with _lock_for(connector_id):
        current = _sessions.get(connector_id)
        if current is not None and current.alive() and _same_capture(current, camera, directory):
            if current.camera.retention_hours != camera.retention_hours:
                current.camera = replace(current.camera, retention_hours=camera.retention_hours)
                prune_archive(directory, keep_seconds=int(camera.retention_hours * 3600))
            return current
        if current is not None:
            logger.warning(
                "Камера %s: новый сеанс, %s",
                connector_id,
                _restart_reason(current, camera, directory),
            )
            await current.stop()
        session = CameraSession(connector_id, camera, directory)
        try:
            await session.start()
        except Exception:
            await session.stop()
            _sessions.pop(connector_id, None)
            raise
        _sessions[connector_id] = session
        return session


def sync_session(connector_id: str, camera: CameraConfig, directory: Path | None = None) -> str:
    """Применяет конфигурацию к уже открытому сеансу.

    Смена адреса, каталога, транспорта, ширины или частоты архива
    открывает сеанс заново. Смена срока хранения только переписывает
    окно очистки и удаляет лишние фрагменты: второй RTSP-клиент
    к камере не открывается.
    """
    directory = directory or camera.segment_dir(connector_id)
    current = _sessions.get(connector_id)
    if (
        current is not None
        and current.alive()
        and _same_capture(current, camera, directory)
    ):
        keep_seconds = int(camera.retention_hours * 3600)
        if current.camera.retention_hours != camera.retention_hours:
            current.camera = camera
            logger.info(
                "Камера %s: хранение %.4g ч",
                connector_id,
                camera.retention_hours,
            )
            note_platform_log(
                connector_id,
                "INFO",
                f"Срок хранения {camera.retention_hours:g} ч.",
            )
            prune_archive(directory, keep_seconds=keep_seconds)
            return "retention"
        prune_archive(directory, keep_seconds=keep_seconds)
        return "kept"
    ensure_session(connector_id, camera, directory)
    return "restart"


def ensure_session(connector_id: str, camera: CameraConfig, directory: Path | None = None) -> None:
    """Запускает сеанс, не дожидаясь первого кадра. Для архивного чтения."""
    directory = directory or camera.segment_dir(connector_id)
    current = _sessions.get(connector_id)
    if (
        current is not None
        and _same_capture(current, camera, directory)
        and current.camera.retention_hours == camera.retention_hours
        and current.alive()
    ):
        _pending.pop(connector_id, None)
        return
    if connector_id in _opening:
        _pending[connector_id] = (camera, directory)
        return
    _opening.add(connector_id)

    async def _open() -> None:
        try:
            await get_session(connector_id, camera, directory)
        except Exception as ex:
            logger.warning(
                "Камера %s не открылась: %s",
                camera.log_target,
                redact_rtsp(str(ex)),
            )
            note_platform_log(
                connector_id,
                "WARNING",
                f"Сеанс не открылся: {redact_rtsp(str(ex))}",
            )
        finally:
            _opening.discard(connector_id)
            nxt = _pending.pop(connector_id, None)
            if nxt is not None:
                ensure_session(connector_id, nxt[0], nxt[1])

    asyncio.create_task(_open())


async def stop_session(connector_id: str) -> bool:
    async with _lock_for(connector_id):
        current = _sessions.pop(connector_id, None)
        if current is None:
            return False
        await current.stop()
        return True


def session_ids() -> list[str]:
    return [connector_id for connector_id, session in _sessions.items() if session.alive()]


def tracked_session_ids() -> list[str]:
    return list(_sessions)


async def stop_all_sessions() -> None:
    for connector_id in list(_sessions):
        await stop_session(connector_id)


async def _spawn_ffmpeg(args: list[str], timeout: float):
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as ex:
        raise VideoRuntimeError("Не найден ffmpeg. Установите его в образ платформы.") from ex
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError as ex:
        proc.kill()
        await proc.wait()
        raise VideoRuntimeError("ffmpeg не успел отдать кадр или фрагмент.") from ex
    if proc.returncode != 0:
        message = redact_rtsp((stderr or b"").decode("utf-8", errors="replace"))[-400:]
        raise VideoRuntimeError(message or "ffmpeg завершился с ошибкой.")
    return stdout or b""


async def run_ffmpeg(args: list[str], timeout: float) -> None:
    await _spawn_ffmpeg(args, timeout)


async def run_ffmpeg_bytes(args: list[str], timeout: float) -> bytes:
    stdout = await _spawn_ffmpeg(args, timeout)
    if not stdout:
        raise VideoRuntimeError("ffmpeg завершился без данных.")
    return stdout
