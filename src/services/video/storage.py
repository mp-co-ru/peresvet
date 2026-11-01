"""Хранилище видео: путь архива и срок хранения для тегов типа 6.

Коннектор отдаёт RTSP. Хранилище с ``prsEntityTypeCode`` = 3 забирает этот
поток, пишет его на диск и отдаёт клиентам. Каталог камеры —
``archivePath/<id коннектора>``.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from src.common import hierarchy
from src.common.consts import CNDataStorageTypes
from src.services.video.archive_config import ArchiveConfig, parse_archive_config
from src.services.video.camera import CameraConfig

VIDEO_STORAGE_TYPE = int(CNDataStorageTypes.CN_DS_VIDEO)
NO_VIDEO_STORAGE = "Тег видеопотока не привязан к хранилищу видео."


class VideoStorageError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def camera_with_storage(camera: CameraConfig, archive: ArchiveConfig, connector_id: str) -> CameraConfig:
    """Подставляет каталог и срок хранения из хранилища. Поток остаётся от коннектора."""
    return replace(
        camera,
        archive_path=archive.path / connector_id,
        retention_hours=archive.retention_hours,
    )


def _first(attrs: dict, name: str) -> Any:
    raw = attrs.get(name)
    if not raw:
        return None
    return raw[0]


def _flag(attrs: dict, name: str, default: bool = True) -> bool:
    raw = _first(attrs, name)
    if raw is None:
        return default
    return str(raw).upper() == "TRUE"


def _json_config(attrs: dict) -> dict:
    raw = _first(attrs, "prsJsonConfigString")
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {}


async def video_storage_for_tag(hierarchy_api, tag_id: str) -> tuple[str, ArchiveConfig]:
    """Активное хранилище видео, к которому привязан тег."""
    storages = await hierarchy_api.search({
        "base": "cn=dataStorages,cn=prs",
        "scope": hierarchy.CN_SCOPE_SUBTREE,
        "filter": {
            "objectClass": ["prsDataStorage"],
            "prsEntityTypeCode": [str(VIDEO_STORAGE_TYPE)],
        },
        "attributes": ["prsActive", "prsJsonConfigString", "prsEntityTypeCode"],
    })
    for ds_id, _, attrs in storages or []:
        if not _flag(attrs, "prsActive", default=True):
            continue
        link = await hierarchy_api.search({
            "base": ds_id,
            "scope": hierarchy.CN_SCOPE_SUBTREE,
            "filter": {"objectClass": ["prsDatastorageTagData"], "cn": [tag_id]},
            "attributes": ["cn"],
        })
        if not link:
            continue
        try:
            archive = parse_archive_config(_json_config(attrs))
        except (ValueError, TypeError) as ex:
            raise VideoStorageError(422, str(ex)) from ex
        return str(ds_id), archive
    raise VideoStorageError(424, NO_VIDEO_STORAGE)
