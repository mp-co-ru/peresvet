"""Публичный GET /v1/data/ для тега типа 6.

Платформа проверяет право и узнаёт по RPC, какой процесс отдачи
обслуживает тег. Байты идут по HTTP на этот процесс. Если подписчика
на ключ нет, в историю JSON запрос не проваливается.
"""

from __future__ import annotations

import asyncio

from starlette.requests import Request

from src.common.authorization import authorize_action
from src.services.video.errors import error_response
from src.services.video.locate import locate_delivery, missing_delivery
from src.services.video.lookup import VideoFailure, resolve_video_get
from src.services.video.upstream_http import proxy_stream


def wants_live_audio(payload) -> bool:
    extra = getattr(payload, "model_extra", None) or {}
    return str(extra.get("audio") or "") in {"1", "true", "True"}


_hierarchy_lock = asyncio.Lock()


async def _connect_video_hierarchy():
    """tags_app_api не держит LDAP. Для видеотега соединение открывается здесь."""
    from src.common.hierarchy import Hierarchy
    from src.common.svc_settings import SvcSettings

    hierarchy_api = Hierarchy(SvcSettings().ldap_url)
    await hierarchy_api.connect()
    return hierarchy_api


async def hierarchy_api(app):
    found = getattr(app, "_hierarchy", None)
    if found is not None:
        return found
    async with _hierarchy_lock:
        found = getattr(app, "_hierarchy", None)
        if found is not None:
            return found
        connected = await _connect_video_hierarchy()
        try:
            app._hierarchy = connected
        except Exception:
            pass
        return connected


async def maybe_video_data_response(app, payload, request: Request | None = None):
    """None — это не видеотег, вызывающий продолжает обычное чтение истории."""
    try:
        resolved = await resolve_video_get(await hierarchy_api(app), payload)
    except Exception as ex:
        app._logger.exception(f"{app._config.svc_name} :: ошибка поиска камеры: {ex}")
        return error_response(500, "Не удалось найти камеру для тега.")
    if resolved is None:
        return None
    if isinstance(resolved, VideoFailure):
        return error_response(resolved.code, resolved.message)

    body = {"tagId": [resolved.tag_id]}
    await authorize_action(
        f"{app._config.hierarchy['class']}.data_get",
        resource={"tagIds": [resolved.tag_id]},
        payload=body,
    )
    if request is None:
        return error_response(500, "Нет HTTP-запроса для проксирования на сервис отдачи.")
    base = await locate_delivery(app, resolved.tag_id)
    if not base:
        return error_response(503, missing_delivery())
    return await proxy_stream(request, f"{base}/v1/data/")
