from __future__ import annotations

from typing import Any, Sequence

import src.common.times as t


def normalize_point_xyq(v: Any) -> tuple[int, Any, int | None] | Any:
    """Normalize a historical data point to (x, y, q).

    Platform-wide convention:
    - [y]          -> x = now,  y = y, q = None
    - [x, y]       -> x = ts(x), y = y, q = None
    - [x, y, q]    -> x = ts(x), y = y, q = q
    - [] / None    -> x = now,  y = None, q = None

    If `v` is not a sequence, it is returned unchanged (to let validation fail upstream).
    """
    if v is None:
        return (t.ts(None), None, None)

    if isinstance(v, (str, bytes, bytearray, dict)):
        # strings/dicts are not treated as point sequences
        return v

    if not isinstance(v, Sequence):
        return v

    n = len(v)
    if n == 0:
        return (t.ts(None), None, None)
    if n == 1:
        return (t.ts(None), v[0], None)
    if n == 2:
        return (t.ts(v[0]), v[1], None)
    if n == 3:
        return (t.ts(v[0]), v[1], v[2])

    return v


def coerce_tag_data_items_for_data_set(raw: Any) -> list[Any]:
    """Поле ``data`` тега в ``data_set``: всегда список элементов для поочерёдной обработки.

    Обычно это ``[[x,y,q], ...]``. Одна точка может прийти плоским ``[x,y]`` или
    ``[x,y,q]`` (первый элемент — скаляр времени, не вложенная последовательность);
    тогда оборачиваем в ``[точка]``. Кортеж одной точки без списка — в ``[tuple]``.
    """
    if raw is None:
        return []
    if isinstance(raw, tuple):
        return [raw]
    if not isinstance(raw, list):
        return [raw]
    if len(raw) >= 2 and not isinstance(raw[0], (list, tuple)):
        return [raw]
    return raw


def tag_data_points_json_safe(points: list[Any]) -> list[Any]:
    """Точки для JSON-RPC ответа: стандартный ``json.dumps`` не сериализует ``tuple``."""
    out: list[Any] = []
    for p in points:
        if isinstance(p, tuple):
            out.append(list(p))
        else:
            out.append(p)
    return out

