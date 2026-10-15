"""HTTP между платформой, отдачей и подхватом.

Живой поток, звук, снимок и фрагмент идут этим каналом.
В RabbitMQ их нет: сообщение брокера не рассчитано на бесконечный MJPEG
и на многомегабайтный mp4.
"""

from __future__ import annotations

import aiohttp
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

from src.services.video.errors import error_response


def _with_query(url: str, request: Request | None) -> str:
    if request is None or not request.url.query:
        return url
    join = "&" if "?" in url else "?"
    return f"{url}{join}{request.url.query}"


async def proxy_stream(request: Request | None, url: str, *, forward_query: bool = True):
    """Копирует ответ, не собирая его в память. Для живого потока таймаута чтения нет."""
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=5, sock_read=None)
    session = aiohttp.ClientSession(timeout=timeout)
    target = _with_query(url, request) if forward_query else url
    try:
        upstream = await session.get(target)
    except aiohttp.ClientError as ex:
        await session.close()
        return error_response(502, f"Сервис видео недоступен: {ex}")

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


async def proxy_exchange(request: Request, url: str, timeout_total: float = 15):
    """Короткий запрос: метод, query и тело уходят как есть. Так платформа зовёт отдачу."""
    timeout = aiohttp.ClientTimeout(total=timeout_total, sock_connect=5)
    session = aiohttp.ClientSession(timeout=timeout)
    headers = {}
    content_type = request.headers.get("content-type")
    if content_type:
        headers["Content-Type"] = content_type
    try:
        upstream = await session.request(
            request.method,
            _with_query(url, request),
            data=await request.body(),
            headers=headers,
        )
        payload = await upstream.read()
    except aiohttp.ClientError as ex:
        await session.close()
        return error_response(502, f"Сервис видео недоступен: {ex}")
    media_type = upstream.headers.get("Content-Type", "application/json")
    status = upstream.status
    upstream.release()
    await session.close()
    return Response(payload, status_code=status, media_type=media_type)


async def proxy_bytes(request: Request, url: str):
    """Короткий POST с уже прочитанным телом. Так уходят куски звука микрофона."""
    data = await request.body()
    timeout = aiohttp.ClientTimeout(total=20, sock_connect=5)
    session = aiohttp.ClientSession(timeout=timeout)
    try:
        upstream = await session.post(
            url,
            data=data,
            headers={"Content-Type": request.headers.get("content-type", "application/octet-stream")},
        )
        payload = await upstream.read()
    except aiohttp.ClientError as ex:
        await session.close()
        return error_response(502, f"Сервис видео недоступен: {ex}")
    media_type = upstream.headers.get("Content-Type", "application/json")
    status = upstream.status
    upstream.release()
    await session.close()
    return Response(payload, status_code=status, media_type=media_type)


async def proxy_upload(request: Request, url: str):
    """Передаёт тело запроса дальше, не собирая его целиком. Так идёт звук микрофона."""
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=5, sock_read=None)
    session = aiohttp.ClientSession(timeout=timeout)

    async def chunks():
        async for chunk in request.stream():
            if chunk:
                yield chunk

    try:
        upstream = await session.post(
            url,
            data=chunks(),
            headers={"Content-Type": request.headers.get("content-type", "application/octet-stream")},
        )
        payload = await upstream.read()
    except aiohttp.ClientError as ex:
        await session.close()
        return error_response(502, f"Сервис видео недоступен: {ex}")
    media_type = upstream.headers.get("Content-Type", "application/json")
    status = upstream.status
    upstream.release()
    await session.close()
    return Response(payload, status_code=status, media_type=media_type)


async def proxy_json(url: str, payload: dict, timeout_total: float = 15):
    """JSON без исходного HTTP-запроса. Так отдача зовёт OnVif на подхвате."""
    timeout = aiohttp.ClientTimeout(total=timeout_total, sock_connect=5)
    session = aiohttp.ClientSession(timeout=timeout)
    try:
        upstream = await session.post(url, json=payload)
        body = await upstream.read()
    except aiohttp.ClientError as ex:
        await session.close()
        return error_response(502, f"Сервис видео недоступен: {ex}")
    media_type = upstream.headers.get("Content-Type", "application/json")
    status = upstream.status
    upstream.release()
    await session.close()
    return Response(body, status_code=status, media_type=media_type)
