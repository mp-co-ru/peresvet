"""Правила каталога методов: привязки, проверка вызова, родители кэша инициаторов.

Загрузчик пакетов и сервисы methods импортируют этот модуль.
Код партнёрских пакетов (worker.py) отсюда не импортируется.
"""
from __future__ import annotations

import json
from typing import Any

VALUE_TYPE_CODES = frozenset({1, 2, 3, 4})
INITIATOR_PARENT_CLASSES = frozenset({"prsTag", "prsAlert"})
BINDING_FIELDS = {
    "tag": frozenset({"binding", "tagId"}),
    "literal": frozenset({"binding", "value", "valueTypeCode"}),
    "constant": frozenset({"binding", "constantId"}),
}


def error(code: int, message: str) -> dict:
    return {"id": None, "error": {"code": code, "message": message}}


def ldap_first(attrs: dict | None, key: str, default: Any = None) -> Any:
    if not attrs:
        return default
    raw = attrs.get(key, default)
    if isinstance(raw, list):
        raw = raw[0] if raw else default
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode()
    return default if raw is None else raw


def as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(value.strip())
        except ValueError:
            return None
    if isinstance(value, list) and value:
        return as_int(value[0])
    return None


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def catalog_id_from_message(mes: dict) -> tuple[str | None, dict | None]:
    attrs = mes.get("attributes") or {}
    if not isinstance(attrs, dict):
        attrs = {}
    top = mes.get("catalogMethodId")
    attr = attrs.get("prsCatalogMethodId")
    if isinstance(attr, list):
        attr = attr[0] if attr else None
    top_id = None if is_blank(top) else str(top).strip()
    attr_id = None if is_blank(attr) else str(attr).strip()
    if top_id and attr_id and top_id != attr_id:
        return None, error(422, "catalogMethodId и prsCatalogMethodId различаются.")
    return top_id or attr_id, None


def parameter_attributes(item: Any) -> dict:
    if not isinstance(item, dict):
        return {}
    attrs = item.get("attributes") or {}
    return attrs if isinstance(attrs, dict) else {}


def config_of_parameter(attrs: dict) -> dict:
    raw = attrs.get("prsJsonConfigString")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if raw is None:
        return {}
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("prsJsonConfigString параметра должен быть объектом JSON.")
        return parsed
    if isinstance(raw, dict):
        return raw
    raise ValueError("prsJsonConfigString параметра должен быть объектом JSON.")


def validate_binding(cfg: dict) -> str | None:
    if not isinstance(cfg, dict):
        return "Привязка параметра должна быть объектом JSON."
    if "routingKey" in cfg and not is_blank(cfg.get("routingKey")):
        return "При использовании метода каталога поле routingKey запрещено."
    kind = cfg.get("binding")
    if kind not in BINDING_FIELDS:
        return "Привязка параметра должна быть tag, literal или constant."
    allowed = BINDING_FIELDS[kind]
    extra = set(cfg) - allowed
    if extra:
        return "В привязке параметра есть поля вне допустимого набора."
    if kind == "tag" and is_blank(cfg.get("tagId")):
        return "Привязка tag требует tagId."
    if kind == "constant" and is_blank(cfg.get("constantId")):
        return "Привязка constant требует constantId."
    if kind == "literal":
        if "value" not in cfg:
            return "Привязка literal требует value."
        if as_int(cfg.get("valueTypeCode")) not in VALUE_TYPE_CODES:
            return "valueTypeCode привязки должен быть 1, 2, 3 или 4."
    return None


def validate_catalog_parameter(attrs: dict) -> str | None:
    if as_int(attrs.get("prsIndex")) is None:
        return "У параметра метода каталога должен быть prsIndex."
    if as_int(attrs.get("prsValueTypeCode")) not in VALUE_TYPE_CODES:
        return "У параметра метода каталога prsValueTypeCode должен быть 1, 2, 3 или 4."
    return None


def validate_method_message(
    mes: dict,
    *,
    placement: str,
    catalog_id: str | None,
    catalog_address: str | None,
    require_address: bool = False,
) -> dict | None:
    """Проверяет создание и изменение метода. Меняет ``mes`` под правила каталога.

    ``placement`` — ``catalog`` (корень cn=methods или папка prsModelNode внутри него),
    ``instance`` (prsTag или prsAlert) либо иное значение, которое дальше
    отклонит проверка родителя.
    """
    attrs = mes.setdefault("attributes", {})
    if not isinstance(attrs, dict):
        return error(422, "Атрибуты метода должны быть объектом.")

    if not catalog_id:
        if attrs.get("prsCatalogMethodId") in (None, ""):
            attrs.pop("prsCatalogMethodId", None)
        mes.pop("catalogMethodId", None)

    if placement == "catalog":
        if catalog_id:
            return error(422, "Метод каталога не ссылается на другой метод каталога.")
        initiators = mes.get("initiatedBy")
        if isinstance(initiators, str):
            initiators = [initiators]
        if initiators:
            return error(422, "У метода каталога не задаются инициаторы.")
        if "prsEntityTypeCode" in attrs and attrs.get("prsEntityTypeCode") is not None:
            if as_int(attrs.get("prsEntityTypeCode")) != 0:
                return error(422, "У метода каталога prsEntityTypeCode должен быть 0.")
        else:
            attrs["prsEntityTypeCode"] = 0
        if require_address or "prsMethodAddress" in attrs:
            if is_blank(attrs.get("prsMethodAddress")):
                return error(422, "У метода каталога должен быть prsMethodAddress.")
        for item in mes.get("parameters") or []:
            message = validate_catalog_parameter(parameter_attributes(item))
            if message:
                return error(422, message)
        return None

    if catalog_id:
        if is_blank(catalog_address):
            return error(422, "У метода каталога нет prsMethodAddress.")
        attrs["prsCatalogMethodId"] = catalog_id
        attrs["prsMethodAddress"] = catalog_address
        mes["catalogMethodId"] = catalog_id
        if "prsEntityTypeCode" in attrs and attrs.get("prsEntityTypeCode") is not None:
            if as_int(attrs.get("prsEntityTypeCode")) not in (0, 1):
                return error(422, "prsEntityTypeCode экземпляра метода должен быть 0 или 1.")
        for item in mes.get("parameters") or []:
            try:
                config_of_parameter(parameter_attributes(item))
            except (ValueError, json.JSONDecodeError) as ex:
                return error(422, str(ex))
    return None


def numeric_of(value: Any) -> int | float | None:
    """Число из литерала или из конверта legacy data_get. None и нечисловые значения — None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            if any(ch in text for ch in ".eE"):
                return float(text)
            return int(text)
        except ValueError:
            return None
    if isinstance(value, dict):
        try:
            point = value["data"][0]["data"][0]
        except (KeyError, IndexError, TypeError):
            return None
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return None
        return numeric_of(point[1])
    return None


def numeric_compatible(type_code: Any, value: Any) -> bool:
    code = as_int(type_code)
    if code not in (1, 2):
        return True
    number = numeric_of(value)
    if number is None:
        return False
    if code == 1 and isinstance(number, float) and not number.is_integer():
        return False
    return True


def _sort_index(item: dict) -> int:
    index = as_int(item.get("index"))
    return 10**9 if index is None else index


def catalog_call_error(catalog_parameters: list[dict], resolved: list[dict]) -> str | None:
    """Арность и числовая совместимость (коды 1 и 2) до вызова patio."""
    expected = sorted(catalog_parameters or [], key=_sort_index)
    actual = sorted(resolved or [], key=_sort_index)
    if len(expected) != len(actual):
        return (
            f"Число параметров {len(actual)} не совпадает с методом каталога ({len(expected)})."
        )
    for catalog_parameter, resolved_parameter in zip(expected, actual):
        code = catalog_parameter.get("valueTypeCode")
        if numeric_compatible(code, resolved_parameter.get("data")):
            continue
        name = catalog_parameter.get("cn") or catalog_parameter.get("index")
        return f"Параметр «{name}» не совместим с типом {code}."
    return None


async def parent_allows_initiator_cache(hierarchy, method_id: str) -> bool:
    """Кэш инициаторов только у методов тега и тревоги."""
    try:
        parent_id, _ = await hierarchy.get_parent(method_id)
    except Exception:
        return False
    if not parent_id:
        return False
    try:
        parent_class = await hierarchy.get_node_class(parent_id)
    except Exception:
        return False
    return parent_class in INITIATOR_PARENT_CLASSES
