"""Отбор точек перед записью в хранилище (TagsApp.data_set).

Правила задаются атрибутом LDAP ``prsMaxLineDev`` и типом значения тега
(``prsValueTypeCode``). Подробнее: ``docs/tag_data_set_filtering.md``.

Тип ``CN_TABLE`` (табличный / интеграционный тег): ``prsMaxLineDev`` не
применяется; точки в хранилище не отсекаются этим модулем (кроме явной смены
качества — тогда точка всегда принимается).
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

    Порядок правил: смена качества → всегда пишем; для ``CN_TABLE`` дальше
    ничего не отсекаем; иначе — общие правила (в т.ч. пара None/None) и
    ``prsMaxLineDev`` по типу тега.
    """
    if _quality_changed(prev_q, new_q):
        return False
    if value_type_code == TVT.CN_TABLE:
        return False
    # Видеопоток: в шину попадают только отметки качества, не кадры.
    # Повтор пустого значения с тем же качеством не пишем.
    if value_type_code == TVT.CN_VIDEO:
        return prev_y is None and new_y is None

    if prev_y is None and new_y is None:
        return True

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


def _as_xyq(point: Any) -> tuple[Any, Any, Any] | None:
    if not isinstance(point, (list, tuple)) or len(point) < 1:
        return None
    y = point[1] if len(point) > 1 else None
    q = point[2] if len(point) > 2 else None
    return (point[0], y, q)


def history_points_to_insert(
    batch: list[Any],
    existing: list[Any],
    *,
    update: bool,
    value_type_code: int,
    max_line_dev: float,
) -> tuple[list[tuple[Any, Any, Any]], list[Any]]:
    """Какие точки пачки писать в историю и какие метки при ``prsUpdate`` заменить.

    ``existing`` — уже лежащие рядом строки ``(x, y, q)``: предшественник,
    строки внутри интервала пачки и наследник. Для любого тега:

    * ``update`` — на одну метку остаётся последнее значение пачки;
    * ``max_line_dev > 0`` — новое значение не ставится в ряд с таким же
      соседним (те же правила, что ``should_discard_data_point``, включая
      смену качества).

    Возвращает ``(точки к вставке, метки к удалению)``. Метки удаляются и
    тогда, когда новое значение на них не проходит порог: старая строка этой
    метки уже недействительна.
    """
    batch_pts = [point for raw in batch if (point := _as_xyq(raw)) is not None]
    if update:
        last_by_x: dict[Any, tuple[Any, Any, Any]] = {}
        for point in batch_pts:
            last_by_x[point[0]] = point
        batch_pts = [last_by_x[x] for x in sorted(last_by_x)]
        delete_xs = list(last_by_x)
    else:
        batch_pts = sorted(batch_pts, key=lambda point: point[0])
        delete_xs = []

    existing_pts = [point for raw in existing if (point := _as_xyq(raw)) is not None]
    if delete_xs:
        replace = set(delete_xs)
        existing_pts = [point for point in existing_pts if point[0] not in replace]

    events: list[tuple[str, tuple[Any, Any, Any]]] = [("old", point) for point in existing_pts]
    events.extend(("new", point) for point in batch_pts)
    events.sort(key=lambda item: (item[1][0], 0 if item[0] == "old" else 1))

    apply_dev = max_line_dev > 0
    kept: list[tuple[str, tuple[Any, Any, Any]]] = []
    prev: tuple[Any, Any, Any] | None = None
    for kind, point in events:
        if kind == "old":
            kept.append((kind, point))
            prev = point
            continue
        if apply_dev and prev is not None and should_discard_data_point(
            value_type_code, max_line_dev, prev[1], prev[2], point[1], point[2]
        ):
            continue
        kept.append((kind, point))
        prev = point

    if apply_dev:
        changed = True
        while changed:
            changed = False
            reduced: list[tuple[str, tuple[Any, Any, Any]]] = []
            for index, (kind, point) in enumerate(kept):
                if kind == "new" and index + 1 < len(kept):
                    nxt = kept[index + 1][1]
                    if should_discard_data_point(
                        value_type_code, max_line_dev, point[1], point[2], nxt[1], nxt[2]
                    ):
                        changed = True
                        continue
                reduced.append((kind, point))
            kept = reduced

    return [point for kind, point in kept if kind == "new"], delete_xs


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
