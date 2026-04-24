"""Поиск активного виртуального метода (prsEntityTypeCode = 1) под тегом."""

from __future__ import annotations

from typing import Any

# ldap.SCOPE_ONELEVEL (без импорта ldap на уровне модуля)
_SCOPE_ONELEVEL = 1


async def find_active_virtual_method_id(hierarchy: Any, tag_id: str) -> str | None:
    """Активный метод с prsEntityTypeCode=1 под тегом (при нескольких — минимальный prsIndex)."""
    payload = {
        "base": tag_id,
        "scope": _SCOPE_ONELEVEL,
        "filter": {"objectClass": ["prsMethod"], "prsActive": ["TRUE"]},
        "attributes": ["cn", "prsEntityTypeCode", "prsIndex"],
    }
    rows = await hierarchy.search(payload=payload)
    if not rows:
        return None
    candidates: list[tuple[tuple[int, str], str]] = []
    for row in rows:
        attrs = row[2]
        raw_code = attrs.get("prsEntityTypeCode", ["0"])
        try:
            if int(raw_code[0]) != 1:
                continue
        except Exception:
            continue
        ix = attrs.get("prsIndex", [None])[0]
        try:
            sort_ix = int(ix) if ix is not None else 1_000_000_000
        except Exception:
            sort_ix = 1_000_000_000
        candidates.append(((sort_ix, row[0]), row[0]))
    if not candidates:
        return None
    candidates.sort(key=lambda z: z[0])
    return candidates[0][1]
