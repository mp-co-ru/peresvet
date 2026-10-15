"""Отдача: allow-list тегов и адрес этого процесса для платформы.

Модельной подписки нет. ``nodes`` проверяется в HTTP-обработчике.
Поиск камеры на каждый запрос идёт в LDAP, отдельный кэш тегов не ведётся.
"""

from __future__ import annotations

import sys

sys.path.append(".")

from src.common.app_svc import AppSvc
from src.services.video.locate import DELIVERY_LOCATE, bind_keys
from src.services.video.ownership import http_base, serves
from src.services.video.video_delivery_settings import VideoDeliverySettings


class VideoDelivery(AppSvc):
    def _set_handlers(self):
        # Без super(): ключи prsTag.model и videoDelivery.model не вешаются.
        for key in bind_keys(DELIVERY_LOCATE, self._config.nodes):
            self._handlers[key] = self._locate

    async def _locate(self, mes: dict, routing_key: str | None = None):
        tag_id = str((mes or {}).get("tagId") or "")
        if not tag_id or not serves(self._config.nodes, tag_id):
            return {
                "error": {
                    "code": 404,
                    "message": "Этот сервис отдачи не обслуживает тег.",
                }
            }
        base = http_base(self._config)
        if not base:
            return {
                "error": {
                    "code": 500,
                    "message": "У сервиса отдачи не задан http_base_url.",
                }
            }
        return {"baseUrl": base}


settings = VideoDeliverySettings()

app = VideoDelivery(settings=settings, title="VideoDelivery")
