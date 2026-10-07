"""Сервис камер: один RTSP-сеанс на активный коннектор-камеру.

Подписка на ``prsConnector.model.created/updated/deleted`` — общая для
сервисов сущности. Голос ``may_update`` разрешает правку: видеосервер
не блокирует сохранение коннектора. После ``updated`` конфигурация
читается из LDAP и применяется к сеансу. Обход раз в 20 секунд
подхватывает камеры, которые уже были в каталоге до старта сервиса,
и повторяет очистку архива, если сообщение было пропущено.
"""

from __future__ import annotations

import asyncio
import sys

sys.path.append(".")

from src.common import hierarchy
from src.common.app_svc import AppSvc
from src.services.video.camera import camera_from_connector_attributes
from src.services.video.presence import configure_presence
from src.services.video.runtime import (
    stop_all_sessions,
    stop_session,
    sync_session,
    tracked_session_ids,
)
from src.services.video.video_app_settings import VideoAppSettings


class VideoApp(AppSvc):
    def __init__(self, settings: VideoAppSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)
        self._scan_task: asyncio.Task | None = None

    async def on_startup(self) -> None:
        broker = self._config.broker or {}
        configure_presence(broker.get("amqp_url", ""))
        await super().on_startup()
        self._scan_task = asyncio.create_task(self._scan_loop())

    async def on_shutdown(self) -> None:
        if self._scan_task is not None:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
            self._scan_task = None
        await stop_all_sessions()
        await super().on_shutdown()

    async def _created(self, mes: dict, routing_key: str | None = None):
        conn_id = str((mes or {}).get("id") or "")
        if not conn_id:
            return {"response": True}
        try:
            await self._apply_connector(conn_id)
        except Exception as ex:
            self._logger.warning(
                f"{self._config.svc_name} :: Коннектор {conn_id}: {ex}"
            )
        return {"response": True}

    async def _updated(self, mes: dict, routing_key: str | None = None):
        return await self._created(mes, routing_key)

    async def _deleted(self, mes: dict, routing_key: str | None = None):
        conn_id = str((mes or {}).get("id") or "")
        if conn_id and await stop_session(conn_id):
            self._logger.info(
                f"{self._config.svc_name} :: Камера {conn_id}: сеанс остановлен, коннектор удалён."
            )
        return {"response": True}

    async def _apply_connector(self, conn_id: str) -> None:
        found = await self._hierarchy.search({
            "id": [conn_id],
            "attributes": ["prsActive", "prsJsonConfigString"],
        })
        if not found:
            if await stop_session(conn_id):
                self._logger.info(
                    f"{self._config.svc_name} :: Камера {conn_id}: сеанс остановлен."
                )
            return
        try:
            camera = camera_from_connector_attributes(found[0][2])
        except (ValueError, TypeError) as ex:
            self._logger.warning(
                f"{self._config.svc_name} :: Коннектор {conn_id}: {ex}"
            )
            return
        if camera is None:
            if await stop_session(conn_id):
                self._logger.info(
                    f"{self._config.svc_name} :: Камера {conn_id}: сеанс остановлен."
                )
            return
        outcome = sync_session(conn_id, camera)
        if outcome == "restart":
            self._logger.info(
                f"{self._config.svc_name} :: Камера {conn_id}: сеанс по новой конфигурации."
            )

    async def _scan_loop(self) -> None:
        while True:
            try:
                await self._scan_once()
            except asyncio.CancelledError:
                raise
            except Exception as ex:
                self._logger.warning(f"{self._config.svc_name} :: Ошибка обхода камер: {ex}")
            await asyncio.sleep(20)

    async def _scan_once(self) -> None:
        found = await self._hierarchy.search({
            "base": "cn=connectors,cn=prs",
            "scope": hierarchy.CN_SCOPE_ONELEVEL,
            "filter": {"objectClass": ["prsConnector"]},
            "attributes": ["prsActive", "prsJsonConfigString"],
        })
        seen: set[str] = set()
        for conn_id, _, attrs in found or []:
            try:
                camera = camera_from_connector_attributes(attrs)
            except (ValueError, TypeError) as ex:
                self._logger.warning(
                    f"{self._config.svc_name} :: Коннектор {conn_id}: {ex}"
                )
                continue
            if camera is None:
                continue
            seen.add(conn_id)
            sync_session(conn_id, camera)
        for conn_id in tracked_session_ids():
            if conn_id not in seen:
                await stop_session(conn_id)


settings = VideoAppSettings()

app = VideoApp(settings=settings, title="VideoApp")
