"""Общая обёртка для вычисления JSONata (jsonatapy) в async-контексте."""
from __future__ import annotations

import asyncio
from typing import Any


async def evaluate_jsonata(expr: str, data: Any, *, timeout_ms: int | None = None) -> Any:
    try:
        import jsonatapy  # type: ignore[reportMissingImports]
    except ModuleNotFoundError as ex:
        raise ModuleNotFoundError(
            "Не установлен пакет 'jsonatapy' (нужен для JSONata выражений)."
        ) from ex

    async def run() -> Any:
        return await asyncio.to_thread(jsonatapy.evaluate, expr, data)

    if timeout_ms is None:
        return await run()
    return await asyncio.wait_for(run(), timeout=timeout_ms / 1000)
