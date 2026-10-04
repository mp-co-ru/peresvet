"""Сервис камер: держит по одному RTSP-сеансу на активный коннектор-камеру.

На голоса ``may_update`` коннекторов не подписывается.
"""

from __future__ import annotations

import asyncio
import json
import sys

sys.path.append(".")

from src.common import hierarchy
from src.common.app_svc import AppSvc
from src.services.video.camera import config_is_camera, parse_camera_config
from src.services.video.runtime import ensure_session, session_ids, stop_all_sessions, stop_session
from src.services.video.video_app_settings import VideoAppSettings


def _first(attrs: dict, name: str):
    raw = attrs.get(name)
    if not raw:
        return None
    return raw[0]


class VideoApp(AppSvc):
    def __init__(self, settings: VideoAppSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)
        self._scan_task: asyncio.Task | None = None

    def _set_handlers(self):
        self._handlers = {}

    async def on_startup(self) -> None:
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
            "attributes": ["prsEntityTypeCode", "prsActive", "prsJsonConfigString"],
        })
        seen: set[str] = set()
        for conn_id, _, attrs in found or []:
            active = _first(attrs, "prsActive")
            if active is not None and str(active).upper() != "TRUE":
                continue
            raw = _first(attrs, "prsJsonConfigString")
            try:
                if isinstance(raw, str):
                    raw = json.loads(raw) if raw else {}
                if not config_is_camera(raw or {}):
                    continue
                camera = parse_camera_config(raw or {})
            except (ValueError, json.JSONDecodeError) as ex:
                self._logger.warning(
                    f"{self._config.svc_name} :: Коннектор {conn_id}: {ex}"
                )
                continue
            seen.add(conn_id)
            ensure_session(conn_id, camera)
        for conn_id in session_ids():
            if conn_id not in seen:
                await stop_session(conn_id)


settings = VideoAppSettings()

app = VideoApp(settings=settings, title="VideoApp")
