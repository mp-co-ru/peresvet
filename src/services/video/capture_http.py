"""Внутренний HTTP подхвата. Снаружи его не публикуют: туда ходит только отдача."""

from __future__ import annotations

import asyncio

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.services.video.camera import camera_from_connector_attributes, max_fragment_seconds
from src.services.video.errors import error_response
from src.services.video.lookup import VideoBinding
from src.services.video.media import (
    fragment_response,
    live_audio_response,
    live_response,
    snapshot_response,
)
from src.services.video.onvif_ptz import OnvifError, perform_ptz
from src.services.video.ownership import serves
from src.services.video.runtime import VideoRuntimeError
from src.services.video.talk import (
    CameraTalk,
    CameraTalkError,
    claim_talk,
    release_talk,
    talk_credentials,
)


_NOT_OURS = "Этот сервис подхвата не обслуживает камеру."


async def _load_camera(app, connector_id: str):
    if not serves(app._config.nodes, connector_id):
        return error_response(404, _NOT_OURS)
    found = await app._hierarchy.search({
        "id": [connector_id],
        "attributes": ["prsActive", "prsJsonConfigString"],
    })
    if not found:
        return error_response(404, "Коннектор камеры не найден.")
    try:
        camera = camera_from_connector_attributes(found[0][2])
    except (ValueError, TypeError) as ex:
        return error_response(422, str(ex))
    if camera is None:
        return error_response(404, "Коннектор не является активной камерой.")
    return camera


def _binding(connector_id: str, camera, mode: str, start_us: int | None, finish_us: int | None):
    return VideoBinding(
        tag_id="",
        connector_id=connector_id,
        camera=camera,
        mode=mode,
        start_us=start_us,
        finish_us=finish_us,
    )


def _microseconds(raw: str | None) -> int | None:
    if raw is None or raw == "":
        return None
    return int(raw)


async def capture_live(app, connector_id: str, request: Request | None):
    camera = await _load_camera(app, connector_id)
    if not hasattr(camera, "rtsp_url"):
        return camera
    try:
        return await live_response(_binding(connector_id, camera, "live", None, None), request)
    except VideoRuntimeError as ex:
        return error_response(502, ex.message)
    except FileNotFoundError:
        return error_response(503, "Не найден ffmpeg.")


async def capture_audio(app, connector_id: str, request: Request | None):
    camera = await _load_camera(app, connector_id)
    if not hasattr(camera, "rtsp_url"):
        return camera
    try:
        return await live_audio_response(_binding(connector_id, camera, "live", None, None), request)
    except VideoRuntimeError as ex:
        return error_response(502, ex.message)
    except FileNotFoundError:
        return error_response(503, "Не найден ffmpeg.")


async def capture_snapshot(app, connector_id: str, finish: str | None):
    camera = await _load_camera(app, connector_id)
    if not hasattr(camera, "rtsp_url"):
        return camera
    try:
        finish_us = _microseconds(finish)
    except (TypeError, ValueError):
        return error_response(422, "Некорректная метка finish.")
    try:
        return await snapshot_response(_binding(connector_id, camera, "snapshot", None, finish_us))
    except VideoRuntimeError as ex:
        return error_response(502, ex.message)
    except FileNotFoundError:
        return error_response(503, "Не найден ffmpeg.")


async def capture_fragment(app, connector_id: str, start: str | None, finish: str | None):
    camera = await _load_camera(app, connector_id)
    if not hasattr(camera, "rtsp_url"):
        return camera
    try:
        start_us = _microseconds(start)
        finish_us = _microseconds(finish)
    except (TypeError, ValueError):
        return error_response(422, "Некорректные метки периода.")
    if start_us is None or finish_us is None or finish_us <= start_us:
        return error_response(422, "В периоде видеопотока finish должен быть позже start.")
    if (finish_us - start_us) / 1_000_000 > max_fragment_seconds():
        return error_response(422, "Слишком длинный видеофрагмент.")
    try:
        return await fragment_response(
            _binding(connector_id, camera, "fragment", start_us, finish_us)
        )
    except VideoRuntimeError as ex:
        return error_response(502, ex.message)
    except FileNotFoundError:
        return error_response(503, "Не найден ffmpeg.")


_open_talks: dict[str, CameraTalk] = {}


def _talk_phase(request: Request | None) -> str:
    if request is None:
        return ""
    return str(request.query_params.get("phase") or "").strip()


async def _close_open_talk(connector_id: str) -> None:
    talk = _open_talks.pop(connector_id, None)
    release_talk(connector_id)
    if talk is not None:
        await asyncio.to_thread(talk.close)


async def capture_talk(app, connector_id: str, request: Request | None):
    phase = _talk_phase(request)
    if phase == "close":
        await _close_open_talk(connector_id)
        return Response(status_code=204)
    camera = await _load_camera(app, connector_id)
    if not hasattr(camera, "rtsp_url"):
        return camera
    login = talk_credentials(camera)
    if login is None:
        return error_response(422, "Для разговора нужен пароль камеры в rtspUrl или onvifPassword.")
    if phase == "write":
        talk = _open_talks.get(connector_id)
        if talk is None:
            return error_response(409, "Разговор не начат.")
        data = await request.body()
        if data:
            await asyncio.to_thread(talk.write_pcma, data)
        return Response(status_code=204)
    if phase != "open":
        return error_response(422, "Нужна фаза разговора: open, write или close.")
    await _close_open_talk(connector_id)
    if not claim_talk(connector_id):
        return error_response(409, "Разговор с этой камерой уже идёт.")
    user, password = login
    talk = CameraTalk(camera.onvif_host, user, password)
    try:
        await asyncio.to_thread(talk.start)
    except CameraTalkError as ex:
        release_talk(connector_id)
        return error_response(502, ex.message)
    _open_talks[connector_id] = talk
    return Response(status_code=204)


async def capture_ptz(app, connector_id: str, command: dict):
    camera = await _load_camera(app, connector_id)
    if not hasattr(camera, "rtsp_url"):
        return camera
    try:
        result = await perform_ptz(camera, command)
    except OnvifError as ex:
        return error_response(502, ex.message)
    return JSONResponse(result)
