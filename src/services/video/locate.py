"""Короткий RPC: кто отдаёт тег и кто держит камеру.

В брокер уходит только id и ответ с базовым URL процесса.
Кадры, звук, снимки и фрагменты этим сообщением не едут.
"""

from __future__ import annotations

CAPTURE_LOOKUP = "video.capture.lookup"
DELIVERY_LOCATE = "video.delivery.locate"

_NO_DELIVERY = "Сервис отдачи видео не запущен."
_NO_CAPTURE = "Сервис подхвата видео не запущен."


def capture_lookup_key(connector_id: str) -> str:
    return f"{CAPTURE_LOOKUP}.{connector_id}"


def delivery_locate_key(tag_id: str) -> str:
    return f"{DELIVERY_LOCATE}.{tag_id}"


def bind_keys(prefix: str, nodes) -> list[str]:
    listed = [str(item) for item in (nodes or []) if str(item)]
    if not listed:
        return [f"{prefix}.*"]
    return [f"{prefix}.{item}" for item in listed]


def _base_url(reply) -> str | None:
    if not isinstance(reply, dict) or reply.get("error"):
        return None
    base = str(reply.get("baseUrl") or "").strip().rstrip("/")
    return base or None


async def locate_delivery(app, tag_id: str) -> str | None:
    reply = await app._post_message(
        {"tagId": tag_id},
        reply=True,
        routing_key=delivery_locate_key(tag_id),
    )
    return _base_url(reply)


async def locate_capture(app, connector_id: str) -> str | None:
    reply = await app._post_message(
        {"connectorId": connector_id},
        reply=True,
        routing_key=capture_lookup_key(connector_id),
    )
    return _base_url(reply)


def missing_delivery() -> str:
    return _NO_DELIVERY


def missing_capture() -> str:
    return _NO_CAPTURE
