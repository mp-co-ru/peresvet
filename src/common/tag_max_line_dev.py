"""Отбор точек перед записью в хранилище (TagsApp.data_set).

Правила задаются атрибутом LDAP ``prsMaxLineDev`` и типом значения тега
(``prsValueTypeCode``). Подробнее: ``docs/tag_data_set_filtering.md``.
"""

from __future__ import annotations

import json
import numbers
from decimal import Decimal
from typing import Any

from src.common.consts import CNTagValueTypes as TVT


def parse_prs_max_line_dev_from_ldap_attrs(attrs: dict[str, Any]) -> float:
    """Читает prsMaxLineDev из ответа LDAP (список строк). По умолчанию 0."""
    raw = attrs.get("prsMaxLineDev")
    if not raw or raw[0] is None or raw[0] == "":
        return 0.0
    v = raw[0]
    if isinstance(v, bytes):
        v = v.decode("utf-8", errors="replace").strip()
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _coerce_numeric(y: Any) -> float | None:
    if y is None:
        return None
    if isinstance(y, bool):
        return None
    if isinstance(y, numbers.Real):
        return float(y)
    if isinstance(y, Decimal):
        return float(y)
    if isinstance(y, str):
        try:
            return float(y)
        except ValueError:
            return None
    if isinstance(y, (bytes, bytearray)):
        try:
            return float(y.decode("utf-8", errors="replace").strip())
        except ValueError:
            return None
    item = getattr(y, "item", None)
    if callable(item):
        try:
            return float(item())
        except (TypeError, ValueError, AttributeError):
            pass
    try:
        return float(y)
    except (TypeError, ValueError):
        return None


def _quality_changed(prev_q: Any, new_q: Any) -> bool:
    return prev_q != new_q


def _normalize_for_str_json_equality(value_type_code: int, y: Any) -> Any:
    if y is None:
        return None
    if value_type_code == TVT.CN_STR and isinstance(y, (bytes, bytearray)):
        return y.decode("utf-8", errors="replace")
    if value_type_code == TVT.CN_JSON and isinstance(y, (bytes, bytearray)):
        try:
            return json.loads(y.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, UnicodeError):
            return y.decode("utf-8", errors="replace")
    return y


def _tag_values_equal_for_str_json(value_type_code: int, a: Any, b: Any) -> bool:
    return _normalize_for_str_json_equality(value_type_code, a) == _normalize_for_str_json_equality(
        value_type_code, b
    )


def _discard_numeric_threshold(prev_y: Any, new_y: Any, max_line_dev: float) -> bool:
    """Отбросить из‑за малого отклонения (только для int/double, ``max_line_dev`` > 0)."""
    if max_line_dev <= 0:
        return False
    if new_y is None:
        return False
    new_n = _coerce_numeric(new_y)
    if new_n is None:
        return False
    prev_n = _coerce_numeric(prev_y) if prev_y is not None else None
    if prev_n is None:
        return False
    return abs(new_n - prev_n) < max_line_dev


def should_discard_data_point(
    value_type_code: int,
    max_line_dev: float,
    prev_y: Any,
    prev_q: Any,
    new_y: Any,
    new_q: Any,
) -> bool:
    """True — точку ``(x, new_y, new_q)`` не передавать в хранилище.

    Порядок правил: смена качества → всегда пишем; оба значения None и качество
    то же — не пишем; далее — по типу тега и ``prsMaxLineDev``.
    """
    if _quality_changed(prev_q, new_q):
        return False
    if prev_y is None and new_y is None:
        return True

    if value_type_code == TVT.CN_TABLE:
        return False

    if value_type_code in (TVT.CN_STR, TVT.CN_JSON):
        if max_line_dev <= 0:
            return False
        return _tag_values_equal_for_str_json(value_type_code, prev_y, new_y)

    if value_type_code in (TVT.CN_INT, TVT.CN_DOUBLE):
        return _discard_numeric_threshold(prev_y, new_y, max_line_dev)

    return False


def should_discard_point_for_max_line_dev(
    value_type_code: int,
    max_line_dev: float,
    prev_y: Any,
    new_y: Any,
    prev_q: Any | None = None,
    new_q: Any | None = None,
) -> bool:
    """Обёртка для совместимости: то же, что ``should_discard_data_point``."""
    return should_discard_data_point(
        value_type_code, max_line_dev, prev_y, prev_q, new_y, new_q
    )


def filter_data_points_for_storage(
    points: list[Any],
    value_type_code: int,
    max_line_dev: float,
    prev_y: Any,
    prev_q: Any,
) -> tuple[list[Any], Any, Any]:
    """Фильтрует точки ``(x, y, q)``; возвращает (принятые, последнее y, последнее q)."""
    accepted: list[Any] = []
    last_y = prev_y
    last_q = prev_q
    for p in points:
        if not isinstance(p, (list, tuple)):
            accepted.append(p)
            continue
        if len(p) < 2:
            accepted.append(p)
            continue
        y = p[1]
        q = p[2] if len(p) >= 3 else None
        if should_discard_data_point(
            value_type_code, max_line_dev, last_y, last_q, y, q
        ):
            continue
        accepted.append(p)
        last_y, last_q = y, q
    if not accepted:
        return [], prev_y, prev_q
    return accepted, last_y, last_q


def filter_points_by_max_line_dev(
    points: list[Any],
    value_type_code: int,
    max_line_dev: float,
    prev_y: Any,
    prev_q: Any | None = None,
) -> tuple[list[Any], Any]:
    """Устаревшая сигнатура: возвращает только (точки, last_y). Используйте ``filter_data_points_for_storage``."""
    acc, ly, _ = filter_data_points_for_storage(
        points, value_type_code, max_line_dev, prev_y, prev_q
    )
    return acc, ly
