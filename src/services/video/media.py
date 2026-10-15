"""Байты камеры: их отдаёт только тот процесс, который уже держит RTSP.

Живой MJPEG и звук читаются из сеанса. Снимок и фрагмент собираются
из файлов архива этого же сеанса, вторым подключением к камере это не является.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from pathlib import Path

from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import FileResponse, Response, StreamingResponse

from src.services.video.camera import (
    fragment_ffmpeg_args,
    list_segments,
    live_snapshot_skew_us,
    segment_at,
    segment_seconds,
    segments_overlapping,
    snapshot_file_args,
    write_concat_list,
)
from src.services.video.errors import error_response
from src.services.video.lookup import VideoBinding
from src.services.video.runtime import (
    VideoRuntimeError,
    ensure_session,
    get_session,
    run_ffmpeg,
    run_ffmpeg_bytes,
)

logger = logging.getLogger("video")
_NO_FRAME = "Нет записи камеры на этот момент."


def _camera_dir(binding: VideoBinding) -> Path:
    return binding.camera.segment_dir(binding.connector_id)


async def live_response(binding: VideoBinding, request: Request | None) -> StreamingResponse:
    session = await get_session(binding.connector_id, binding.camera, _camera_dir(binding))
    queue = session.subscribe()

    async def chunks():
        try:
            while True:
                if request is not None and await request.is_disconnected():
                    break
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk
        finally:
            session.unsubscribe(queue)

    return StreamingResponse(
        chunks(),
        media_type="multipart/x-mixed-replace; boundary=ffmpeg",
    )


async def live_audio_response(binding: VideoBinding, request: Request | None) -> Response:
    session = await get_session(binding.connector_id, binding.camera, _camera_dir(binding))
    if not session._want_audio:
        return error_response(404, "У камеры нет звука в потоке.")
    queue = session.subscribe_audio()

    async def chunks():
        try:
            while True:
                if request is not None and await request.is_disconnected():
                    break
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk
        finally:
            session.unsubscribe_audio(queue)

    return StreamingResponse(chunks(), media_type="audio/mpeg")


async def snapshot_response(binding: VideoBinding) -> Response:
    directory = _camera_dir(binding)
    ensure_session(binding.connector_id, binding.camera, directory)
    now_us = int(time.time() * 1_000_000)
    finish_us = int(binding.finish_us if binding.finish_us is not None else now_us)
    segments = list_segments(directory, segment_seconds_value=segment_seconds(), now_us=now_us)
    recent = abs(now_us - finish_us) <= live_snapshot_skew_us()
    if recent:
        jpeg = await _snapshot_recent(directory, segments)
    else:
        segment = segment_at(segments, finish_us)
        if segment is None:
            return error_response(404, _NO_FRAME)
        offset = (finish_us - segment.start_us) / 1_000_000
        try:
            jpeg = await run_ffmpeg_bytes(snapshot_file_args(segment.path, offset), timeout=20)
        except VideoRuntimeError as ex:
            logger.warning("Снимок %s не собран: %s", segment.path.name, ex.message)
            return error_response(404, _NO_FRAME)
    if not jpeg:
        return error_response(404, _NO_FRAME)
    return Response(content=jpeg, media_type="image/jpeg")


async def _snapshot_tail_offset(path: Path) -> float:
    """Сдвиг к последнему кадру. Метки внутри сегмента начинаются не с нуля."""
    from src.services.video.camera import ffmpeg_bin

    probe = "ffprobe"
    ffmpeg = ffmpeg_bin()
    if ffmpeg != "ffmpeg":
        probe = str(Path(ffmpeg).with_name("ffprobe"))
    try:
        proc = await asyncio.create_subprocess_exec(
            probe, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        duration = float((stdout or b"").decode().strip())
    except (ValueError, OSError, TimeoutError):
        return 0.0
    return max(0.0, duration - 0.4)


async def _snapshot_recent(directory: Path, segments) -> bytes:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        current = list_segments(
            directory,
            segment_seconds_value=segment_seconds(),
            now_us=int(time.time() * 1_000_000),
        ) or segments
        if current:
            offset = await _snapshot_tail_offset(current[-1].path)
            try:
                return await run_ffmpeg_bytes(
                    snapshot_file_args(current[-1].path, offset),
                    timeout=15,
                )
            except VideoRuntimeError:
                try:
                    return await run_ffmpeg_bytes(
                        snapshot_file_args(current[-1].path, 0),
                        timeout=15,
                    )
                except VideoRuntimeError:
                    pass
        await asyncio.sleep(0.4)
    raise VideoRuntimeError("Камера ещё не записала кадр.")


async def fragment_response(binding: VideoBinding) -> Response:
    directory = _camera_dir(binding)
    ensure_session(binding.connector_id, binding.camera, directory)
    now_us = int(time.time() * 1_000_000)
    start_us = int(binding.start_us or 0)
    finish_us = int(binding.finish_us or now_us)
    chosen = segments_overlapping(
        list_segments(directory, segment_seconds_value=segment_seconds(), now_us=now_us),
        start_us,
        finish_us,
    )
    if not chosen:
        return error_response(404, "Нет записи камеры за этот период.")
    directory.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix="fragment-", dir=directory))
    concat_list = tmp_dir / "list.txt"
    output = tmp_dir / "fragment.mp4"

    def _cleanup() -> None:
        for path in tmp_dir.glob("*"):
            path.unlink(missing_ok=True)
        tmp_dir.rmdir()

    write_concat_list(concat_list, [segment.path for segment in chosen])
    offset = max(0.0, (start_us - chosen[0].start_us) / 1_000_000)
    duration = max(0.1, (finish_us - start_us) / 1_000_000)
    try:
        await run_ffmpeg(
            fragment_ffmpeg_args(concat_list, output, offset, duration),
            timeout=180,
        )
    except Exception:
        _cleanup()
        raise
    if not output.is_file():
        _cleanup()
        return error_response(502, "Не удалось собрать видеофрагмент.")

    return FileResponse(
        output,
        media_type="video/mp4",
        filename="fragment.mp4",
        background=BackgroundTask(_cleanup),
    )
