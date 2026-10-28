"""Пример конфигурации коннектора для формы в конфигураторе.

Платформа публикует запрос в ``prs2conn.<id>``. Коннектор отвечает
в ``conn2prs/<id>`` тем же действием ``prsConnector.config_example``.
Ответ описывает ключи ``prsJsonConfigString``: понятное имя, подсказку,
тип, пример значения, значение по умолчанию и образец конфигурации целиком.
Платформа хранит ответ в кэше, чтобы форму можно было показать, когда
коннектор уже не на связи.
"""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

CONFIG_EXAMPLE_ACTION = "prsConnector.config_example"
CONFIG_EXAMPLE_TIMEOUT_SEC = 3.0
_MAX_FIELDS = 80
_MAX_TEXT = 500
_MAX_NAME = 120
_MAX_ENUM = 30
_MAX_EXAMPLE_CHARS = 2000
_MAX_CONFIG_EXAMPLE_CHARS = 32000
_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
_FIELD_TYPES = {"string", "integer", "number", "boolean", "json", "object"}


def config_example_cache_key(conn_id: str, svc_name: str) -> str:
    return f"{conn_id}.{svc_name}.config_example"


def connector_uuid(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return str(UUID(value.strip()))
    except (ValueError, AttributeError):
        return None


def _clip(value: Any, limit: int) -> str:
    return str(value).strip()[:limit]


def _example_matches(type_name: str, value: Any) -> bool:
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "json":
        try:
            encoded = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            return False
        return len(encoded) <= _MAX_EXAMPLE_CHARS
    return False


def _normalize_field(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    key = raw.get("key")
    if not isinstance(key, str) or not _KEY_RE.fullmatch(key) or key.count(".") > 5:
        return None
    type_name = raw.get("type") or "string"
    if type_name not in _FIELD_TYPES:
        return None
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        name = key
    field: dict[str, Any] = {
        "key": key,
        "name": _clip(name, _MAX_NAME),
        "type": type_name,
    }
    description = raw.get("description")
    if isinstance(description, str) and description.strip():
        field["description"] = _clip(description, _MAX_TEXT)
    enum = raw.get("enum")
    if enum is not None:
        if type_name != "string" or not isinstance(enum, list):
            return None
        choices: list[str] = []
        for item in enum[:_MAX_ENUM]:
            if not isinstance(item, str) or not item.strip():
                return None
            choice = _clip(item, _MAX_NAME)
            if choice not in choices:
                choices.append(choice)
        if not choices:
            return None
        field["enum"] = choices
    if "example" in raw and raw["example"] is not None:
        example = raw["example"]
        if not _example_matches(type_name, example):
            return None
        if "enum" in field and example not in field["enum"]:
            return None
        if type_name == "json":
            try:
                encoded = json.dumps(example, ensure_ascii=False)
            except (TypeError, ValueError):
                return None
            if len(encoded) > _MAX_EXAMPLE_CHARS:
                return None
        field["example"] = example
    if "default" in raw:
        if type_name == "object":
            return None
        default = raw["default"]
        if not _example_matches(type_name, default):
            return None
        if "enum" in field and default not in field["enum"]:
            return None
        field["default"] = default
    return field


def _normalize_config_document(raw: Any) -> dict | None:
    """Образец ``prsJsonConfigString`` целиком. Не объект — ответ неверный."""
    if not isinstance(raw, dict):
        return None
    try:
        encoded = json.dumps(raw, ensure_ascii=False)
    except (TypeError, ValueError):
        return None
    if len(encoded) > _MAX_CONFIG_EXAMPLE_CHARS:
        return None
    return raw


def normalize_config_example(data: Any) -> dict | None:
    """Разобрать ответ коннектора. Некорректное сообщение отбрасывается целиком."""
    if not isinstance(data, dict):
        return None
    conn_id = connector_uuid(data.get("id"))
    fields_raw = data.get("fields")
    if conn_id is None or not isinstance(fields_raw, list) or not fields_raw:
        return None
    fields: list[dict] = []
    seen: set[str] = set()
    for raw in fields_raw[:_MAX_FIELDS]:
        field = _normalize_field(raw)
        if field is None or field["key"] in seen:
            return None
        seen.add(field["key"])
        fields.append(field)
    if len(fields_raw) > _MAX_FIELDS:
        return None
    result: dict[str, Any] = {"id": conn_id, "fields": fields}
    if "example" in data:
        document = _normalize_config_document(data.get("example"))
        if document is None:
            return None
        result["example"] = document
    return result


def unwrap_redis_json(value: Any) -> Any:
    """RedisJSON GET с path ``$`` оборачивает документ в список из одного элемента."""
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
        return value[0]
    return value


def public_config_example(
    conn_id: str,
    stored: dict | None,
    source: str,
    connector_available: bool,
) -> dict:
    fields = list(stored.get("fields") or []) if isinstance(stored, dict) else []
    received_at = stored.get("receivedAt") if isinstance(stored, dict) else None
    example = stored.get("example") if isinstance(stored, dict) else None
    if not isinstance(example, dict):
        example = None
    if not fields:
        return {
            "id": conn_id,
            "fields": [],
            "example": None,
            "source": "none",
            "connectorAvailable": connector_available,
            "receivedAt": None,
        }
    if source not in ("connector", "cache"):
        source = "cache"
    return {
        "id": conn_id,
        "fields": fields,
        "example": example,
        "source": source,
        "connectorAvailable": connector_available,
        "receivedAt": received_at,
    }
