"""HTTP-вход видеосервера.

Запускается отдельным контейнером. Платформа проксирует сюда чтение
тега типа 6 после проверки прав. Здесь один сеанс RTSP на камеру
и раздача потока всем подключённым зрителям.
"""

from __future__ import annotations

import os
import sys

import uvicorn
from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import JSONResponse

sys.path.append(".")

from src.services.video.http_response import maybe_video_data_response
from src.services.video.query import payload_from_request
from src.services.video.video_app_svc import app

router = APIRouter()


@router.get("/v1/data/")
async def video_data_get(request: Request):
    try:
        payload = payload_from_request(request)
    except Exception as ex:
        return JSONResponse(
            {"error": {"code": 422, "message": f"Несоответствие входных данных: {ex}"}},
            status_code=422,
        )
    media = await maybe_video_data_response(app, payload, request)
    if media is None:
        return JSONResponse(
            {
                "error": {
                    "code": 422,
                    "message": "Видеосервер принимает только тег видеопотока.",
                }
            },
            status_code=422,
        )
    return media


app.include_router(router)


if __name__ == "__main__":
    port = int(os.environ.get("VIDEO_HTTP_PORT", "8090"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
