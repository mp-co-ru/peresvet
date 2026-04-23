"""
Разбор prsJsonConfigString параметра метода.

Поддерживаются:
- внутренний запрос платформы: routingKey + message, опционально responseJsonata;
- только JSONata по клиентскому запросу GET /v1/data: clientJsonata;
- устаревший режим: тело запроса GET /v1/data (поле tagId), опционально responseJsonata.
"""
from __future__ import annotations

import copy
import json
from typing import Any, Awaitable, Callable

from src.common.jsonata_eval import evaluate_jsonata


def parse_parameter_config(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return {}
        return json.loads(s)
    raise TypeError(f"prsJsonConfigString параметра: ожидался dict или str, получили {type(raw)}")


async def resolve_parameter_value(
    cfg: dict,
    *,
    post_message: Callable[..., Awaitable[Any]],
    client_request: dict | None,
    initiator_finish: Any,
    initiator_point: list | tuple | None,
) -> Any:
    """
    initiator_finish — метка времени инициатора (для legacy data_get подставляется в finish).
    initiator_point — сырая точка (x,y,q) при запуске от тега/расписания.
    """
    rk = cfg.get("routingKey")
    if isinstance(rk, str) and rk.strip():
        msg = cfg.get("message")
        if msg is None:
            msg = {}
        if not isinstance(msg, dict):
            raise ValueError("Поле message параметра метода должно быть объектом JSON.")
        raw = await post_message(mes=msg, reply=True, routing_key=rk.strip())
        expr = cfg.get("responseJsonata")
        if isinstance(expr, str) and expr.strip():
            return await evaluate_jsonata(expr.strip(), raw)
        return raw

    cj = cfg.get("clientJsonata")
    if isinstance(cj, str) and cj.strip():
        ctx = client_request if isinstance(client_request, dict) else {}
        if not ctx and initiator_point is not None:
            p = initiator_point
            ctx = {
                "finish": initiator_finish,
                "start": None,
                "point": {"x": p[0], "y": p[1] if len(p) > 1 else None, "q": p[2] if len(p) > 2 else None},
            }
        return await evaluate_jsonata(cj.strip(), ctx)

    if "tagId" in cfg:
        request = copy.deepcopy(cfg)
        request["finish"] = initiator_finish
        raw = await post_message(
            mes=request,
            reply=True,
            routing_key="prsTag.app_api_client.data_get.*",
        )
        expr = cfg.get("responseJsonata")
        if isinstance(expr, str) and expr.strip():
            return await evaluate_jsonata(expr.strip(), raw)
        return raw

    raise ValueError(
        "Некорректный prsJsonConfigString параметра метода: "
        "нужен routingKey, clientJsonata или tagId (запрос GET /v1/data)."
    )
