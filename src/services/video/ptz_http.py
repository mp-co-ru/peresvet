"""HTTP управления камерой: платформа проверяет право, видеосервер говорит с OnVif."""

from __future__ import annotations

import json

import aiohttp
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.common.authorization import authorize_action
from src.services.video.http_response import _error, _hierarchy_api
from src.services.video.lookup import VideoFailure, resolve_camera_control
from src.services.video.onvif_ptz import OnvifError, perform_ptz
from src.services.video.proxy import video_server_url


def _command_from_request(request: Request, body: dict) -> tuple[str, dict]:
    tag_id = str(body.get("tagId") or request.query_params.get("tagId") or "").strip()
    command = {key: value for key, value in body.items() if key != "tagId"}
    command["action"] = body.get("action") or request.query_params.get("action") or "status"
    for key in ("pan", "tilt", "zoom"):
        if command.get(key) is None and request.query_params.get(key) is not None:
            command[key] = request.query_params.get(key)
    if not command.get("token"):
        command["token"] = body.get("preset") or request.query_params.get("token")
    if request.method == "GET":
        command["action"] = "status"
    return tag_id, command


async def _read_body(request: Request) -> dict:
    raw = await request.body()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def proxy_ptz(request: Request):
    base = video_server_url()
    if not base:
        return _error(503, "Видеосервер не задан.")
    url = f"{base}/v1/ptz/"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    timeout = aiohttp.ClientTimeout(total=15, sock_connect=5)
    session = aiohttp.ClientSession(timeout=timeout)
    try:
        upstream = await session.request(
            request.method,
            url,
            data=await request.body(),
            headers={"Content-Type": request.headers.get("content-type", "application/json")},
        )
        payload = await upstream.read()
    except aiohttp.ClientError as ex:
        await session.close()
        return _error(502, f"Видеосервер недоступен: {ex}")
    media_type = upstream.headers.get("Content-Type", "application/json")
    status = upstream.status
    upstream.release()
    await session.close()
    return Response(payload, status_code=status, media_type=media_type)


async def ptz_response(app, request: Request):
    body = await _read_body(request)
    tag_id, command = _command_from_request(request, body)
    if not tag_id:
        return _error(422, "Нужен tagId тега видеопотока.")
    try:
        resolved = await resolve_camera_control(await _hierarchy_api(app), tag_id)
    except Exception as ex:
        app._logger.exception(f"{app._config.svc_name} :: ошибка поиска камеры: {ex}")
        return _error(500, "Не удалось найти камеру для тега.")
    if isinstance(resolved, VideoFailure):
        return _error(resolved.code, resolved.message)
    connector_id, camera = resolved
    if video_server_url():
        await authorize_action(
            "prsConnector.connector_command",
            request=request,
            resource={"id": connector_id},
            payload=command,
        )
        return await proxy_ptz(request)
    try:
        result = await perform_ptz(camera, command)
    except OnvifError as ex:
        return _error(502, ex.message)
    return JSONResponse(result)


def build_ptz_router(app):
    from fastapi import APIRouter

    router = APIRouter()

    @router.api_route("/v1/ptz/", methods=["GET", "POST"])
    async def ptz(request: Request):
        return await ptz_response(app, request)

    return router
