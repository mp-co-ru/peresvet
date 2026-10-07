"""Ответ GET /v1/data/ для тега типа 6: поток, снимок или фрагмент."""

from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from pathlib import Path

from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse

from src.common.authorization import authorize_action
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
from src.services.video.lookup import VideoBinding, VideoFailure, resolve_video_get
from src.services.video.proxy import proxy_video_get, video_server_url
from src.services.video.runtime import (
    VideoRuntimeError,
    ensure_session,
    get_session,
    run_ffmpeg,
    run_ffmpeg_bytes,
)

logger = logging.getLogger("video")
_NO_FRAME = "Нет записи камеры на этот момент."


def _error(code: int, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=code)


_hierarchy_lock = asyncio.Lock()


async def _connect_video_hierarchy():
    """tags_app_api не держит LDAP. Для видеотега соединение открывается здесь."""
    from src.common.hierarchy import Hierarchy
    from src.common.svc_settings import SvcSettings

    hierarchy_api = Hierarchy(SvcSettings().ldap_url)
    await hierarchy_api.connect()
    return hierarchy_api


async def _hierarchy_api(app):
    found = getattr(app, "_hierarchy", None)
    if found is not None:
        return found
    async with _hierarchy_lock:
        found = getattr(app, "_hierarchy", None)
        if found is not None:
            return found
        connected = await _connect_video_hierarchy()
        try:
            app._hierarchy = connected
        except Exception:
            pass
        return connected


async def maybe_video_data_response(app, payload, request: Request | None = None):
    """None — это не видеотег, вызывающий продолжает обычное чтение истории."""
    try:
        resolved = await resolve_video_get(await _hierarchy_api(app), payload)
    except Exception as ex:
        app._logger.exception(f"{app._config.svc_name} :: ошибка поиска камеры: {ex}")
        return _error(500, "Не удалось найти камеру для тега.")
    if resolved is None:
        return None
    if isinstance(resolved, VideoFailure):
        return _error(resolved.code, resolved.message)

    body = {"tagId": [resolved.tag_id]}
    await authorize_action(
        f"{app._config.hierarchy['class']}.data_get",
        resource={"tagIds": [resolved.tag_id]},
        payload=body,
    )
    if video_server_url():
        if request is None:
            return _error(500, "Нет HTTP-запроса для проксирования на видеосервер.")
        return await proxy_video_get(request)
    try:
        if resolved.mode == "live":
            return await _live(resolved, request)
        if resolved.mode == "snapshot":
            return await _snapshot(resolved)
        return await _fragment(resolved)
    except VideoRuntimeError as ex:
        return _error(502, ex.message)
    except FileNotFoundError:
        return _error(503, "Не найден ffmpeg.")


async def _live(binding: VideoBinding, request: Request | None) -> StreamingResponse:
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


async def _snapshot(binding: VideoBinding) -> Response:
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
            return _error(404, _NO_FRAME)
        offset = (finish_us - segment.start_us) / 1_000_000
        try:
            jpeg = await run_ffmpeg_bytes(snapshot_file_args(segment.path, offset), timeout=20)
        except VideoRuntimeError as ex:
            logger.warning("Снимок %s не собран: %s", segment.path.name, ex.message)
            return _error(404, _NO_FRAME)
    if not jpeg:
        return _error(404, _NO_FRAME)
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


async def _fragment(binding: VideoBinding) -> Response:
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
        return _error(404, "Нет записи камеры за этот период.")
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
        return _error(502, "Не удалось собрать видеофрагмент.")

    return FileResponse(
        output,
        media_type="video/mp4",
        filename="fragment.mp4",
        background=BackgroundTask(_cleanup),
    )


def _camera_dir(binding: VideoBinding) -> Path:
    return binding.camera.segment_dir(binding.connector_id)
