"""HTTP отдачи: тег резолвится здесь, байты забираются у подхвата по HTTP."""

from __future__ import annotations

from starlette.requests import Request

from src.services.video.errors import error_response
from src.services.video.http_response import hierarchy_api, wants_live_audio
from src.services.video.locate import locate_capture, missing_capture
from src.services.video.lookup import VideoFailure, resolve_camera_control, resolve_video_get
from src.services.video.ownership import serves
from src.services.video.ptz_http import command_from_request, read_json_body
from src.services.video.query import payload_from_request
from src.services.video.upstream_http import proxy_bytes, proxy_json, proxy_stream

_NOT_OURS = "Этот сервис отдачи не обслуживает тег."


def _foreign(nodes, tag_ids: list[str]) -> bool:
    return any(not serves(nodes, tag_id) for tag_id in tag_ids)


def capture_media_url(base: str, binding, audio: bool) -> str:
    root = f"{base}/internal/video/{binding.connector_id}"
    if audio:
        return f"{root}/audio"
    if binding.mode == "live":
        return f"{root}/live"
    if binding.mode == "snapshot":
        return f"{root}/snapshot?finish={int(binding.finish_us)}"
    return (
        f"{root}/fragment?start={int(binding.start_us)}&finish={int(binding.finish_us)}"
    )


async def delivery_data_response(app, request: Request):
    try:
        payload = payload_from_request(request)
    except Exception as ex:
        return error_response(422, f"Несоответствие входных данных: {ex}")
    tag_ids = [str(item) for item in payload.tagId]
    if _foreign(app._config.nodes, tag_ids):
        return error_response(404, _NOT_OURS)
    try:
        resolved = await resolve_video_get(await hierarchy_api(app), payload)
    except Exception as ex:
        app._logger.exception(f"{app._config.svc_name} :: ошибка поиска камеры: {ex}")
        return error_response(500, "Не удалось найти камеру для тега.")
    if resolved is None:
        return error_response(422, "Видеосервер принимает только тег видеопотока.")
    if isinstance(resolved, VideoFailure):
        return error_response(resolved.code, resolved.message)
    audio = wants_live_audio(payload)
    if audio and resolved.mode != "live":
        return error_response(422, "Звук камеры есть только у живого потока.")
    base = await locate_capture(app, resolved.connector_id)
    if not base:
        return error_response(503, missing_capture())
    return await proxy_stream(
        request,
        capture_media_url(base, resolved, audio),
        forward_query=False,
    )


async def delivery_ptz_response(app, request: Request):
    body = await read_json_body(request)
    tag_id, command = command_from_request(request, body)
    if not tag_id:
        return error_response(422, "Нужен tagId тега видеопотока.")
    if not serves(app._config.nodes, tag_id):
        return error_response(404, _NOT_OURS)
    try:
        resolved = await resolve_camera_control(await hierarchy_api(app), tag_id)
    except Exception as ex:
        app._logger.exception(f"{app._config.svc_name} :: ошибка поиска камеры: {ex}")
        return error_response(500, "Не удалось найти камеру для тега.")
    if isinstance(resolved, VideoFailure):
        return error_response(resolved.code, resolved.message)
    connector_id, _camera = resolved
    base = await locate_capture(app, connector_id)
    if not base:
        return error_response(503, missing_capture())
    return await proxy_json(f"{base}/internal/video/{connector_id}/ptz", command)


async def delivery_talk_response(app, request: Request):
    tag_id = str(request.query_params.get("tagId") or "").strip()
    if not tag_id:
        return error_response(422, "Нужен tagId тега видеопотока.")
    if not serves(app._config.nodes, tag_id):
        return error_response(404, _NOT_OURS)
    try:
        resolved = await resolve_camera_control(await hierarchy_api(app), tag_id)
    except Exception as ex:
        app._logger.exception(f"{app._config.svc_name} :: ошибка поиска камеры: {ex}")
        return error_response(500, "Не удалось найти камеру для тега.")
    if isinstance(resolved, VideoFailure):
        return error_response(resolved.code, resolved.message)
    connector_id, _camera = resolved
    base = await locate_capture(app, connector_id)
    if not base:
        return error_response(503, missing_capture())
    phase = str(request.query_params.get("phase") or "").strip()
    query = f"?phase={phase}" if phase else ""
    return await proxy_bytes(request, f"{base}/internal/video/{connector_id}/talk{query}")
