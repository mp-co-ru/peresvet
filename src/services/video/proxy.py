"""Проксирование GET /v1/data/ видеотега на отдельный видеосервер.

Несколько зрителей подключаются к видеосерверу. Там один сеанс RTSP
раздаётся всем, а платформа только проверяет право чтения тега.
"""

from __future__ import annotations

import os

import aiohttp
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse


def video_server_url() -> str | None:
    raw = os.environ.get("VIDEO_SERVER_URL", "").strip()
    return raw.rstrip("/") or None


async def proxy_video_get(request: Request):
    base = video_server_url()
    if not base:
        return JSONResponse(
            {"error": {"code": 503, "message": "Видеосервер не задан."}},
            status_code=503,
        )
    url = f"{base}/v1/data/"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=5, sock_read=None)
    session = aiohttp.ClientSession(timeout=timeout)
    try:
        upstream = await session.get(url)
    except aiohttp.ClientError as ex:
        await session.close()
        return JSONResponse(
            {"error": {"code": 502, "message": f"Видеосервер недоступен: {ex}"}},
            status_code=502,
        )

    async def body():
        try:
            async for chunk in upstream.content.iter_chunked(65536):
                if request is not None and await request.is_disconnected():
                    break
                yield chunk
        finally:
            upstream.release()
            await session.close()

    media_type = upstream.headers.get("Content-Type", "application/octet-stream")
    return StreamingResponse(body(), status_code=upstream.status, media_type=media_type)
