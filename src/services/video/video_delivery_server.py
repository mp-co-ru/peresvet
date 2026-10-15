"""HTTP отдачи. Порт только в сети compose, наружу его не пробрасывают."""

from __future__ import annotations

import os
import sys

import uvicorn
from fastapi import APIRouter
from starlette.requests import Request

sys.path.append(".")

from src.services.video.delivery_http import (
    delivery_data_response,
    delivery_ptz_response,
    delivery_talk_response,
)
from src.services.video.video_delivery_svc import app

router = APIRouter()


@router.get("/v1/data/")
async def video_data_get(request: Request):
    return await delivery_data_response(app, request)


@router.api_route("/v1/ptz/", methods=["GET", "POST"])
async def ptz(request: Request):
    return await delivery_ptz_response(app, request)


@router.post("/v1/talk/")
async def talk(request: Request):
    return await delivery_talk_response(app, request)


app.include_router(router)


if __name__ == "__main__":
    port = int(os.environ.get("VIDEO_HTTP_PORT", app._config.http_port))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
