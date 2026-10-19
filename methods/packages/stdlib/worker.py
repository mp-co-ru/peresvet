"""Арифметика каталога методов. Отдельный процесс patio, проект methods_app.

Сервис methods_app этот модуль не импортирует. Запуск:

    python methods/packages/stdlib/worker.py

Адрес брокера берётся из переменной окружения amqp_url.
Принимаются и конверт legacy data_get, и обычное число.
None, нечисловое значение и деление на ноль возвращают {"error": "..."}:
тег при таком ответе не записывается.
"""
from __future__ import annotations

import asyncio
import os

from patio import AsyncExecutor, Registry
from patio_rabbitmq import RabbitMQBroker

rpc = Registry(project="methods_app", auto_naming=False)


def _amqp_url() -> str:
    return os.environ.get("amqp_url") or os.environ.get("AMQP_URL") or "amqp://prs:Peresvet21@rabbitmq/"


def _unwrap(value):
    if isinstance(value, dict) and "data" in value:
        try:
            point = value["data"][0]["data"][0]
        except (KeyError, IndexError, TypeError):
            return value
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            return point[1]
    return value


def _number(value):
    if value is None:
        return None, "значение отсутствует"
    value = _unwrap(value)
    if value is None:
        return None, "значение отсутствует"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, "нечисловое значение"
    return value, None


def _apply(left, right, operation, *, divide=False):
    a, error_a = _number(left)
    b, error_b = _number(right)
    if error_a or error_b or a is None or b is None:
        return {"error": error_a or error_b or "нечисловое значение"}
    if divide and b == 0:
        return {"error": "деление на ноль"}
    try:
        return operation(a, b)
    except Exception as ex:
        return {"error": str(ex)}


@rpc("prs.stdlib.add")
async def add(a, b):
    return _apply(a, b, lambda x, y: x + y)


@rpc("prs.stdlib.sub")
async def sub(a, b):
    return _apply(a, b, lambda x, y: x - y)


@rpc("prs.stdlib.mul")
async def mul(a, b):
    return _apply(a, b, lambda x, y: x * y)


@rpc("prs.stdlib.div")
async def div(a, b):
    return _apply(a, b, lambda x, y: x / y, divide=True)


async def main() -> None:
    async with AsyncExecutor(rpc, max_workers=4) as executor:
        while True:
            try:
                async with RabbitMQBroker(executor, amqp_url=_amqp_url()) as broker:
                    await broker.join()
            except KeyboardInterrupt:
                return
            except Exception:
                await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
