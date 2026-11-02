"""Подхват: один RTSP-сеанс на камеру из списка ``nodes``.

Подписка на ``prsConnector.model.*`` — общая для сервисов сущности.
При непустом ``nodes`` базовый ``AppSvc`` не подписывает ``created``:
подхват добавляет эту подписку сам и оставляет только камеры из списка.
Правка хранилища видео приходит сообщением ``prsDataStorage.model.updated``.
Голос ``may_*`` разрешает правку и не останавливает сеанс: иначе
сохранение коннектора ждало бы камеру. При старте каталог читается один раз:
брокер не повторяет уже существующие камеры.
"""

from __future__ import annotations

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
from src.services.video.storage import VIDEO_STORAGE_TYPE
from src.services.video.video_capture_settings import VideoCaptureSettings


class VideoCapture(AppSvc):
    def __init__(self, settings: VideoCaptureSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    def _add_app_handlers(self):
        for key in bind_keys(CAPTURE_LOOKUP, self._config.nodes):
            self._handlers[key] = self._lookup
        # Базовый AppSvc при непустом nodes на created не подписывается.
        self._handlers["prsConnector.model.created"] = self._created
        # Уведомления, не голос may_*: иначе подхват участвовал бы в правке тега.
        self._handlers["prsTag.model.updated.*"] = self._tag_updated
        self._handlers["prsTag.model.deleted.*"] = self._tag_deleted
        self._handlers["prsDataStorage.model.created"] = self._storage_changed
        self._handlers["prsDataStorage.model.updated.*"] = self._storage_changed
        self._handlers["prsDataStorage.model.deleted.*"] = self._storage_deleted
        self._handlers["prsConnector.app_api.command.*"] = self._command

    async def on_startup(self) -> None:
        bind_platform_log(self._post_message)
        broker = self._config.broker or {}
        configure_presence(broker.get("amqp_url", ""))
        await super().on_startup()
        try:
            from src.services.video.webrtc_fanout import ensure_fanout

            await ensure_fanout()
        except Exception as ex:
            self._logger.warning(f"{self._config.svc_name} :: WebRTC: {ex}")
        try:
            await self._load_cameras()
        except Exception as ex:
            self._logger.warning(f"{self._config.svc_name} :: Ошибка чтения камер при старте: {ex}")

    async def on_shutdown(self) -> None:
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

    async def _storage_changed(self, mes: dict, routing_key: str | None = None):
        return await self._apply_storage(str((mes or {}).get("id") or ""), deleted=False)

    async def _storage_deleted(self, mes: dict, routing_key: str | None = None):
        return await self._apply_storage(str((mes or {}).get("id") or ""), deleted=True)

    async def _apply_storage(self, ds_id: str, deleted: bool) -> dict:
        if not ds_id:
            return {"response": True}
        try:
            if not deleted and not await self._storage_is_video(ds_id):
                return {"response": True}
            connector_ids: list[str] = []
            if not deleted:
                connector_ids.extend(await self._connectors_using_storage(ds_id))
            connector_ids.extend(tracked_session_ids())
            seen: set[str] = set()
            for conn_id in connector_ids:
                if conn_id in seen or not serves(self._config.nodes, conn_id):
                    continue
                seen.add(conn_id)
                await self._apply_connector(conn_id)
        except Exception as ex:
            self._logger.warning(
                f"{self._config.svc_name} :: Хранилище {ds_id}: {ex}"
            )
        return {"response": True}

    async def _storage_is_video(self, ds_id: str) -> bool:
        found = await self._hierarchy.search({
            "id": [ds_id],
            "attributes": ["prsEntityTypeCode"],
        })
        if not found:
            return False
        raw = found[0][2].get("prsEntityTypeCode")
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else None
        if isinstance(raw, bytes):
            raw = raw.decode()
        try:
            return int(raw) == VIDEO_STORAGE_TYPE
        except (TypeError, ValueError):
            return False

    async def _connectors_using_storage(self, ds_id: str) -> list[str]:
        links = await self._hierarchy.search({
            "base": ds_id,
            "scope": hierarchy.CN_SCOPE_SUBTREE,
            "filter": {"objectClass": ["prsDatastorageTagData"]},
            "attributes": ["cn"],
        })
        connector_ids: list[str] = []
        for _link_id, _, attrs in links or []:
            tag_id = attrs.get("cn")
            if isinstance(tag_id, (list, tuple)):
                tag_id = tag_id[0] if tag_id else None
            if isinstance(tag_id, bytes):
                tag_id = tag_id.decode()
            if not tag_id:
                continue
            conn_id = await connector_id_for_tag(self._hierarchy, str(tag_id))
            if conn_id:
                connector_ids.append(conn_id)
        return connector_ids

    async def _load_cameras(self) -> None:
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
