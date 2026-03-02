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

