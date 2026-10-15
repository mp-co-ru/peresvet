"""HTTP подхвата. Порт только в сети compose, наружу его не пробрасывают."""

from __future__ import annotations

import os
import sys

import uvicorn
from fastapi import APIRouter
from starlette.requests import Request

sys.path.append(".")

from src.services.video.capture_http import (
    capture_audio,
    capture_fragment,
    capture_live,
    capture_ptz,
    capture_snapshot,
    capture_talk,
)
from src.services.video.ptz_http import read_json_body
from src.services.video.video_capture_svc import app

router = APIRouter()


@router.get("/internal/video/{connector_id}/live")
async def live(connector_id: str, request: Request):
    return await capture_live(app, connector_id, request)


@router.get("/internal/video/{connector_id}/audio")
async def audio(connector_id: str, request: Request):
    return await capture_audio(app, connector_id, request)


@router.get("/internal/video/{connector_id}/snapshot")
async def snapshot(connector_id: str, request: Request):
    return await capture_snapshot(app, connector_id, request.query_params.get("finish"))


@router.get("/internal/video/{connector_id}/fragment")
async def fragment(connector_id: str, request: Request):
    return await capture_fragment(
        app,
        connector_id,
        request.query_params.get("start"),
        request.query_params.get("finish"),
    )


@router.post("/internal/video/{connector_id}/ptz")
async def ptz(connector_id: str, request: Request):
    return await capture_ptz(app, connector_id, await read_json_body(request))


@router.post("/internal/video/{connector_id}/talk")
async def talk(connector_id: str, request: Request):
    return await capture_talk(app, connector_id, request)


app.include_router(router)


if __name__ == "__main__":
    port = int(os.environ.get("VIDEO_HTTP_PORT", app._config.http_port))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
