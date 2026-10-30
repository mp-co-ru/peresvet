"""Подхват: один RTSP-сеанс на камеру из списка ``nodes``.

Подписка на ``prsConnector.model.*`` — общая для сервисов сущности.
Голос ``may_*`` разрешает правку и не останавливает сеанс: иначе
сохранение коннектора ждало бы камеру. Конфигурация применяется
по ``updated``. Обход раз в 20 секунд закрывает дыру ``created``:
при непустом ``nodes`` базовый ``AppSvc`` на создание не подписывается.
"""

from __future__ import annotations

import asyncio
import sys

sys.path.append(".")

from src.common import hierarchy
from src.common.app_svc import AppSvc
from src.common.consts import CNTagValueTypes
from src.services.video.camera import camera_from_connector_attributes
from src.services.video.locate import CAPTURE_LOOKUP, bind_keys
from src.services.video.lookup import camera_for_session, connector_id_for_tag
from src.services.video.ownership import http_base, serves
from src.services.video.platform_log import bind as bind_platform_log
from src.services.video.platform_log import clear as clear_platform_log
from src.services.video.platform_log import command as command_platform_log
from src.services.video.platform_log import configure as configure_platform_log
from src.services.video.platform_log import note as note_platform_log
from src.services.video.presence import configure_presence
from src.services.video.runtime import (
    stop_all_sessions,
    stop_session,
    sync_session,
    tracked_session_ids,
)
from src.services.video.video_capture_settings import VideoCaptureSettings


class VideoCapture(AppSvc):
    def __init__(self, settings: VideoCaptureSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)
        self._scan_task: asyncio.Task | None = None

    def _add_app_handlers(self):
        for key in bind_keys(CAPTURE_LOOKUP, self._config.nodes):
            self._handlers[key] = self._lookup
        # Уведомления, не голос may_*: иначе подхват участвовал бы в правке тега.
        self._handlers["prsTag.model.updated.*"] = self._tag_updated
        self._handlers["prsTag.model.deleted.*"] = self._tag_deleted
        self._handlers["prsConnector.app_api.command.*"] = self._command

    async def on_startup(self) -> None:
        bind_platform_log(self._post_message)
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

    async def _lookup(self, mes: dict, routing_key: str | None = None):
        connector_id = str((mes or {}).get("connectorId") or "")
        if not connector_id or not serves(self._config.nodes, connector_id):
            return {
                "error": {
                    "code": 404,
                    "message": "Этот сервис подхвата не обслуживает камеру.",
                }
            }
        base = http_base(self._config)
        if not base:
            return {
                "error": {
                    "code": 500,
                    "message": "У сервиса подхвата не задан http_base_url.",
                }
            }
        return {"baseUrl": base}

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

    async def _tag_updated(self, mes: dict, routing_key: str | None = None):
        tag_id = str((mes or {}).get("id") or "")
        if not tag_id:
            return {"response": True}
        try:
            await self._apply_tag(tag_id, deleted=False)
        except Exception as ex:
            self._logger.warning(
                f"{self._config.svc_name} :: Тег {tag_id}: {ex}"
            )
        return {"response": True}

    async def _tag_deleted(self, mes: dict, routing_key: str | None = None):
        tag_id = str((mes or {}).get("id") or "")
        if not tag_id:
            return {"response": True}
        try:
            await self._apply_tag(tag_id, deleted=True)
        except Exception as ex:
            self._logger.warning(
                f"{self._config.svc_name} :: Тег {tag_id}: {ex}"
            )
        return {"response": True}

    async def _apply_tag(self, tag_id: str, deleted: bool) -> None:
        if not deleted:
            found = await self._hierarchy.search({
                "id": tag_id,
                "attributes": ["prsValueTypeCode"],
            })
            if not found:
                return
            try:
                value_type = int(found[0][2]["prsValueTypeCode"][0])
            except (KeyError, IndexError, TypeError, ValueError):
                return
            if value_type != int(CNTagValueTypes.CN_VIDEO):
                return
        connector_id = await connector_id_for_tag(self._hierarchy, tag_id)
        if not connector_id or not serves(self._config.nodes, connector_id):
            return
        await self._apply_connector(connector_id)

    async def _command(self, mes: dict, routing_key: str | None = None):
        conn_id = str((mes or {}).get("id") or "")
        command = (mes or {}).get("command") or {}
        if not conn_id or "logToPlatform" not in command:
            return {}
        if not serves(self._config.nodes, conn_id):
            return {}
        command_platform_log(conn_id, bool(command.get("logToPlatform")))
        return {}

    async def _deleted(self, mes: dict, routing_key: str | None = None):
        conn_id = str((mes or {}).get("id") or "")
        if conn_id:
            clear_platform_log(conn_id)
        if conn_id and await stop_session(conn_id):
            self._logger.info(
                f"{self._config.svc_name} :: Камера {conn_id}: сеанс остановлен, коннектор удалён."
            )
        return {"response": True}

    async def _apply_connector(self, conn_id: str) -> None:
        if not serves(self._config.nodes, conn_id):
            if await stop_session(conn_id):
                self._logger.info(
                    f"{self._config.svc_name} :: Камера {conn_id}: сеанс остановлен, коннектор вне nodes."
                )
            return
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
            configure_platform_log(conn_id, send=False, level="INFO")
            if await stop_session(conn_id):
                self._logger.info(
                    f"{self._config.svc_name} :: Камера {conn_id}: сеанс остановлен."
                )
                note_platform_log(conn_id, "INFO", "Сеанс остановлен.")
            return
        configure_platform_log(
            conn_id,
            send=camera.log_to_platform,
            level=camera.log_level,
            file_name=camera.log_file_name,
            max_bytes=camera.log_max_bytes,
            backup_count=camera.log_backup_count,
        )
        stored = await camera_for_session(self._hierarchy, conn_id, camera)
        if stored is None:
            if await stop_session(conn_id):
                self._logger.info(
                    f"{self._config.svc_name} :: Камера {conn_id}: сеанс остановлен, нет хранилища видео."
                )
            note_platform_log(conn_id, "WARNING", "Нет хранилища видео, сеанс остановлен.")
            return
        outcome = sync_session(conn_id, stored)
        if outcome == "restart":
            self._logger.info(
                f"{self._config.svc_name} :: Камера {conn_id}: сеанс по новой конфигурации."
            )
            note_platform_log(conn_id, "INFO", "Сеанс открыт по новой конфигурации.")

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
        nodes = [str(item) for item in (self._config.nodes or []) if str(item)]
        if nodes:
            found = await self._hierarchy.search({
                "id": nodes,
                "attributes": ["prsActive", "prsJsonConfigString"],
            })
        else:
            found = await self._hierarchy.search({
                "base": "cn=connectors,cn=prs",
                "scope": hierarchy.CN_SCOPE_SUBTREE,
                "filter": {"objectClass": ["prsConnector"]},
                "attributes": ["prsActive", "prsJsonConfigString"],
            })
        seen: set[str] = set()
        for conn_id, _, attrs in found or []:
            if not serves(nodes, conn_id):
                continue
            try:
                camera = camera_from_connector_attributes(attrs)
            except (ValueError, TypeError) as ex:
                self._logger.warning(
                    f"{self._config.svc_name} :: Коннектор {conn_id}: {ex}"
                )
                continue
            if camera is None:
                continue
            configure_platform_log(
                conn_id,
                send=camera.log_to_platform,
                level=camera.log_level,
                file_name=camera.log_file_name,
                max_bytes=camera.log_max_bytes,
                backup_count=camera.log_backup_count,
            )
            stored = await camera_for_session(self._hierarchy, conn_id, camera)
            if stored is None:
                continue
            seen.add(conn_id)
            sync_session(conn_id, stored)
        for conn_id in tracked_session_ids():
            if conn_id not in seen:
                await stop_session(conn_id)


settings = VideoCaptureSettings()

app = VideoCapture(settings=settings, title="VideoCapture")
