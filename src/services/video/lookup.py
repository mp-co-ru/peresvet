"""Поиск тега типа 6 и привязанной к нему камеры."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from src.common import hierarchy
from src.common.consts import CNTagValueTypes
from src.services.video.camera import (
    CameraConfig,
    config_is_camera,
    is_camera_connector,
    max_fragment_seconds,
    parse_camera_config,
    video_get_mode,
)


@dataclass(frozen=True)
class VideoBinding:
    tag_id: str
    connector_id: str
    camera: CameraConfig
    mode: str
    start_us: int | None
    finish_us: int | None


@dataclass(frozen=True)
class VideoFailure:
    code: int
    message: str


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


async def resolve_video_get(hierarchy_api, payload) -> VideoBinding | VideoFailure | None:
    tag_ids = list(payload.tagId)
    if len(tag_ids) != 1:
        kinds = [await _tag_type(hierarchy_api, tag_id) for tag_id in tag_ids]
        if any(kind == int(CNTagValueTypes.CN_VIDEO) for kind in kinds):
            return VideoFailure(422, "Видеопоток читается по одному тегу за запрос.")
        return None

    tag_id = tag_ids[0]
    tag_res = await hierarchy_api.search({
        "id": tag_id,
        "attributes": ["prsValueTypeCode", "prsActive"],
    })
    if not tag_res:
        return None
    attrs = tag_res[0][2]
    try:
        value_type = int(_first(attrs, "prsValueTypeCode"))
    except (TypeError, ValueError):
        return None
    if value_type != int(CNTagValueTypes.CN_VIDEO):
        return None
    if not _flag(attrs, "prsActive", default=True):
        return VideoFailure(409, "Тег видеопотока выключен.")

    fields = set(getattr(payload, "model_fields_set", ()) or ())
    mode = video_get_mode(fields)
    if mode == "unsupported":
        return VideoFailure(
            422,
            "Для видеопотока ключи timeStep и count пока не поддерживаются.",
        )

    connector_id, camera, error = await _camera_for_tag(hierarchy_api, tag_id)
    if error is not None:
        return error
    assert connector_id is not None and camera is not None

    start_us = int(payload.start) if mode == "fragment" else None
    finish_us = None
    if mode == "snapshot":
        finish_us = int(payload.finish)
    elif mode == "fragment":
        finish_us = int(payload.finish)
        if start_us is None or finish_us <= start_us:
            return VideoFailure(422, "В периоде видеопотока finish должен быть позже start.")
        if (finish_us - start_us) / 1_000_000 > max_fragment_seconds():
            return VideoFailure(422, "Слишком длинный видеофрагмент.")

    return VideoBinding(
        tag_id=tag_id,
        connector_id=connector_id,
        camera=camera,
        mode=mode,
        start_us=start_us,
        finish_us=finish_us,
    )


async def _tag_type(hierarchy_api, tag_id: str) -> int | None:
    res = await hierarchy_api.search({
        "id": tag_id,
        "attributes": ["prsValueTypeCode"],
    })
    if not res:
        return None
    try:
        return int(_first(res[0][2], "prsValueTypeCode"))
    except (TypeError, ValueError):
        return None


async def resolve_camera_control(hierarchy_api, tag_id: str):
    """Камера для управления: тег типа 6 и активный коннектор с rtspUrl."""
    tag_res = await hierarchy_api.search({
        "id": tag_id,
        "attributes": ["prsValueTypeCode", "prsActive"],
    })
    if not tag_res:
        return VideoFailure(404, "Тег не найден.")
    attrs = tag_res[0][2]
    try:
        value_type = int(_first(attrs, "prsValueTypeCode"))
    except (TypeError, ValueError):
        return VideoFailure(422, "Управление камерой доступно только для тега видеопотока.")
    if value_type != int(CNTagValueTypes.CN_VIDEO):
        return VideoFailure(422, "Управление камерой доступно только для тега видеопотока.")
    if not _flag(attrs, "prsActive", default=True):
        return VideoFailure(409, "Тег видеопотока выключен.")
    connector_id, camera, error = await _camera_for_tag(hierarchy_api, tag_id)
    if error is not None:
        return error
    return connector_id, camera


async def _camera_for_tag(hierarchy_api, tag_id: str) -> tuple[str | None, CameraConfig | None, VideoFailure | None]:
    connectors = await hierarchy_api.search({
        "base": "cn=connectors,cn=prs",
        "scope": hierarchy.CN_SCOPE_ONELEVEL,
        "filter": {"objectClass": ["prsConnector"]},
        "attributes": ["prsEntityTypeCode", "prsActive", "prsJsonConfigString"],
    })
    for conn_id, _, attrs in connectors or []:
        if not (
            is_camera_connector(_first(attrs, "prsEntityTypeCode"))
            or config_is_camera(_json_config(attrs))
        ):
            continue
        if not _flag(attrs, "prsActive", default=True):
            continue
        link = await hierarchy_api.search({
            "base": conn_id,
            "scope": hierarchy.CN_SCOPE_SUBTREE,
            "filter": {"cn": [tag_id]},
            "attributes": ["cn"],
        })
        if not link:
            continue
        try:
            camera = parse_camera_config(_json_config(attrs))
        except (ValueError, json.JSONDecodeError) as ex:
            return None, None, VideoFailure(422, str(ex))
        return conn_id, camera, None
    return None, None, VideoFailure(
        424,
        "Тег видеопотока не привязан к активному коннектору-камере.",
    )
