"""Публичный обмен SDP: браузер говорит с платформой, кадры идут по WebRTC."""

from __future__ import annotations

from starlette.requests import Request

from src.common.authorization import authorize_action
from src.services.tags.app_api.tags_app_api_svc import DataGet
from src.services.video.errors import error_response
from src.services.video.http_response import hierarchy_api
from src.services.video.locate import locate_delivery, missing_delivery
from src.services.video.lookup import VideoFailure, resolve_video_get
from src.services.video.ptz_http import read_json_body
from src.services.video.upstream_http import proxy_json
from src.services.video.webrtc_sdp import host_from_header


async def webrtc_response(app, request: Request):
    body = await read_json_body(request)
    tag_id = str(body.get("tagId") or request.query_params.get("tagId") or "").strip()
    if not tag_id:
        return error_response(422, "Нужен tagId тега видеопотока.")
    if not str(body.get("sdp") or "").strip():
        return error_response(422, "Нужен SDP offer.")
    try:
        resolved = await resolve_video_get(
            await hierarchy_api(app),
            DataGet.model_validate({"tagId": [tag_id]}),
        )
    except Exception as ex:
        app._logger.exception(f"{app._config.svc_name} :: ошибка поиска камеры: {ex}")
        return error_response(500, "Не удалось найти камеру для тега.")
    if resolved is None:
        return error_response(422, "Видеосервер принимает только тег видеопотока.")
    if isinstance(resolved, VideoFailure):
        return error_response(resolved.code, resolved.message)
    await authorize_action(
        f"{app._config.hierarchy['class']}.data_get",
        request=request,
        resource={"tagIds": [resolved.tag_id]},
        payload={"tagId": [resolved.tag_id]},
    )
    base = await locate_delivery(app, resolved.tag_id)
    if not base:
        return error_response(503, missing_delivery())
    body["tagId"] = resolved.tag_id
    body["advertiseHost"] = host_from_header(request.headers.get("host"))
    return await proxy_json(f"{base}/v1/video/webrtc", body, timeout_total=25)


def build_webrtc_router(app):
    from fastapi import APIRouter

    router = APIRouter()

    @router.post("/v1/video/webrtc")
    async def webrtc(request: Request):
        return await webrtc_response(app, request)

    return router
