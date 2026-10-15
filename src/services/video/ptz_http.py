"""Публичное управление камерой: право проверяется здесь, OnVif выполняет подхват."""

from __future__ import annotations

import json

from starlette.requests import Request
from starlette.responses import JSONResponse

from src.common.authorization import authorize_action
from src.services.video.errors import error_response
from src.services.video.http_response import hierarchy_api
from src.services.video.locate import locate_delivery, missing_delivery
from src.services.video.lookup import VideoFailure, resolve_camera_control
from src.services.video.upstream_http import proxy_bytes, proxy_exchange


def command_from_request(request: Request, body: dict) -> tuple[str, dict]:
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


async def read_json_body(request: Request) -> dict:
    raw = await request.body()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def ptz_response(app, request: Request):
    body = await read_json_body(request)
    tag_id, command = command_from_request(request, body)
    if not tag_id:
        return error_response(422, "Нужен tagId тега видеопотока.")
    try:
        resolved = await resolve_camera_control(await hierarchy_api(app), tag_id)
    except Exception as ex:
        app._logger.exception(f"{app._config.svc_name} :: ошибка поиска камеры: {ex}")
        return error_response(500, "Не удалось найти камеру для тега.")
    if isinstance(resolved, VideoFailure):
        return error_response(resolved.code, resolved.message)
    connector_id, _camera = resolved
    await authorize_action(
        "prsConnector.connector_command",
        request=request,
        resource={"id": connector_id},
        payload=command,
    )
    base = await locate_delivery(app, tag_id)
    if not base:
        return error_response(503, missing_delivery())
    return await proxy_exchange(request, f"{base}/v1/ptz/")


async def talk_response(app, request: Request):
    tag_id = str(request.query_params.get("tagId") or "").strip()
    if not tag_id:
        return error_response(422, "Нужен tagId тега видеопотока.")
    try:
        resolved = await resolve_camera_control(await hierarchy_api(app), tag_id)
    except Exception as ex:
        app._logger.exception(f"{app._config.svc_name} :: ошибка поиска камеры: {ex}")
        return error_response(500, "Не удалось найти камеру для тега.")
    if isinstance(resolved, VideoFailure):
        return error_response(resolved.code, resolved.message)
    connector_id, _camera = resolved
    await authorize_action(
        "prsConnector.connector_command",
        request=request,
        resource={"id": connector_id},
        payload={"action": "talk"},
    )
    base = await locate_delivery(app, tag_id)
    if not base:
        return error_response(503, missing_delivery())
    phase = str(request.query_params.get("phase") or "").strip()
    query = f"tagId={tag_id}"
    if phase:
        query = f"{query}&phase={phase}"
    return await proxy_bytes(request, f"{base}/v1/talk/?{query}")


def build_talk_router(app):
    from fastapi import APIRouter

    router = APIRouter()

    @router.post("/v1/talk/")
    async def talk(request: Request):
        return await talk_response(app, request)

    return router


def build_ptz_router(app):
    from fastapi import APIRouter

    router = APIRouter()

    @router.api_route("/v1/ptz/", methods=["GET", "POST"])
    async def ptz(request: Request):
        return await ptz_response(app, request)

    return router
