"""Общая обёртка для вычисления JSONata (jsonatapy) в async-контексте."""
from __future__ import annotations

import asyncio
import re
from typing import Any

# jsonatapy разбирает цепочки вида ``a.b[0][1]`` иначе, чем jsonata.js в браузере:
# ``data[0].data[0][1]`` даёт ``None``, а ``(data[0].data)[0][1]`` — нужное число.
_JSONATAPY_DATA_INDEX_AMBIGUITY = re.compile(
    r"^(.+?\.data)((?:\[\s*\d+\s*\])+)\s*$",
    re.DOTALL,
)


def _jsonatapy_group_data_index_tail(expr: str) -> str | None:
    s = expr.strip()
    prefix = ""
    if s.startswith("$."):
        prefix = "$."
        rest = s[2:]
    else:
        rest = s
    m = _JSONATAPY_DATA_INDEX_AMBIGUITY.match(rest)
    if not m:
        return None
    base, tail = m.group(1), m.group(2)
    fixed = f"{prefix}({base}){tail}"
    return fixed if fixed != s else None


async def evaluate_jsonata(expr: str, data: Any, *, timeout_ms: int | None = None) -> Any:
    try:
        import jsonatapy  # type: ignore[reportMissingImports]
    except ModuleNotFoundError as ex:
        raise ModuleNotFoundError(
            "Не установлен пакет 'jsonatapy' (нужен для JSONata выражений)."
        ) from ex

    async def run(e: str) -> Any:
        return await asyncio.to_thread(jsonatapy.evaluate, e, data)

    async def run_maybe_timeout(e: str) -> Any:
        if timeout_ms is None:
            return await run(e)
        return await asyncio.wait_for(run(e), timeout=timeout_ms / 1000)

    first = await run_maybe_timeout(expr)
    if first is not None:
        return first
    alt = _jsonatapy_group_data_index_tail(expr)
    if alt is None:
        return None
    return await run_maybe_timeout(alt)
