"""Один процесс ffmpeg на камеру: архив сегментов и раздача живого MJPEG."""

from __future__ import annotations

import asyncio
import logging
import socket
import time
from pathlib import Path

from src.services.video.camera import (
    CameraConfig,
    ffmpeg_bin,
    redact_rtsp,
    segment_seconds,
    session_ffmpeg_args,
)
from src.services.video.presence import drop_camera_presence, hold_camera_presence

logger = logging.getLogger("video")


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
        self._proc: asyncio.subprocess.Process | None = None
        self._pump_task: asyncio.Task | None = None
        self._audio_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._stderr_lines: list[str] = []
        self._want_audio = True
        self._stopped = False
        self._restarting = False

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
        await self._open_process()
        self._pump_task = asyncio.create_task(self._pump())
        try:
            await asyncio.wait_for(self.ready.wait(), timeout=20)
        except TimeoutError as ex:
            await self.stop()
            raise VideoRuntimeError(
                f"Камера {self.camera.log_target} не прислала кадр за 20 с."
            ) from ex
        hold_camera_presence(self.connector_id)

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
        for task in (self._pump_task, self._audio_task, self._stderr_task):
            if task is not None and not task.done():
                task.cancel()
        for queue in list(self.subscribers):
            queue.put_nowait(None)
        self.subscribers.clear()
        self._end_audio()

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
                self._end_audio()
                logger.info(
                    "Камера %s: в RTSP нет звука, сеанс только с картинкой",
                    self.connector_id,
                )
            logger.warning("Камера %s: поток прервался, перезапуск", self.connector_id)
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
                    self.ready.set()
                    self._broadcast(chunk)
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


def _lock_for(connector_id: str) -> asyncio.Lock:
    lock = _locks.get(connector_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[connector_id] = lock
    return lock


def _same_capture(current: CameraSession, camera: CameraConfig, directory: Path) -> bool:
    """Тот же RTSP и та же картинка архива. Срок хранения сюда не входит."""
    stored = current.camera
    return (
        current.url == camera.rtsp_url
        and stored.transport == camera.transport
        and current.directory == directory
        and stored.archive_width == camera.archive_width
        and stored.archive_fps == camera.archive_fps
    )


async def get_session(connector_id: str, camera: CameraConfig, directory: Path | None = None) -> CameraSession:
    directory = directory or camera.segment_dir(connector_id)
    async with _lock_for(connector_id):
        current = _sessions.get(connector_id)
        if (
            current is not None
            and _same_capture(current, camera, directory)
            and current.camera.retention_hours == camera.retention_hours
            and current.alive()
        ):
            return current
        if current is not None:
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
        return

    async def _open() -> None:
        try:
            await get_session(connector_id, camera, directory)
        except Exception as ex:
            logger.warning(
                "Камера %s не открылась: %s",
                camera.log_target,
                redact_rtsp(str(ex)),
            )

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
