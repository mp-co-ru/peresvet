"""
Разбор prsJsonConfigString параметра метода.

Поддерживаются:
- внешний HTTP-запрос: httpRequest (method, url, headers, body), опционально responseJsonata;
- внутренний запрос платформы: routingKey + message, опционально responseJsonata;
- JSONata по объекту клиентского GET /v1/data: clientJsonata;
- без routingKey и без legacy tagId: весь объект клиентского GET /v1/data (или контекст
  инициатора), опционально clientJsonata для выборки полей;
- устаревший режим: тело запроса GET /v1/data (поле tagId), опционально responseJsonata.

Ключ ``clientStub`` (если есть в сохранённом JSON) игнорируется при выполнении — только для UI конфигуратора.

Привязка экземпляра к методу каталога:
- {"binding":"tag","tagId"}
- {"binding":"literal","value","valueTypeCode"}
- {"binding":"constant","constantId"}
"""
from __future__ import annotations

import copy
import json
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit

import aiohttp

from src.common.jsonata_eval import evaluate_jsonata
from src.services.methods.method_catalog import VALUE_TYPE_CODES, as_int, validate_binding

HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"})
HTTP_MAX_BYTES = 1_000_000


def parse_parameter_config(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return {}
        return json.loads(s)
    raise TypeError(f"prsJsonConfigString параметра: ожидался dict или str, получили {type(raw)}")


def _coerce_literal(value: Any, type_code: int) -> Any:
    if type_code == 1:
        number = as_int(value)
        if number is None:
            raise ValueError("Литерал целого типа не является целым числом.")
        return number
    if type_code == 2:
        if isinstance(value, bool) or value is None:
            raise ValueError("Литерал вещественного типа не является числом.")
        if isinstance(value, (int, float)):
            return float(value) if not isinstance(value, int) else value
        try:
            text = str(value).strip()
            return float(text) if any(ch in text for ch in ".eE") else int(text)
        except (TypeError, ValueError) as ex:
            raise ValueError("Литерал вещественного типа не является числом.") from ex
    if type_code == 3:
        return "" if value is None else str(value)
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        return json.loads(text)
    return value


def _http_too_large(raw: bytes) -> None:
    if len(raw) > HTTP_MAX_BYTES:
        raise ValueError("Ответ внешнего запроса больше 1 МБ.")


def prepare_http_request(spec: Any) -> tuple[str, str, dict[str, str], bytes | None]:
    """Проверяет httpRequest и возвращает метод, URL, заголовки и тело."""
    if not isinstance(spec, dict):
        raise ValueError("httpRequest должен быть объектом.")
    method = str(spec.get("method") or "GET").strip().upper()
    if method not in HTTP_METHODS:
        raise ValueError(
            "Метод внешнего запроса должен быть GET, POST, PUT, PATCH, DELETE или HEAD."
        )
    url = spec.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ValueError("У внешнего запроса должен быть URL.")
    url = url.strip()
    if any(ch in url for ch in "\r\n"):
        raise ValueError("URL внешнего запроса содержит перевод строки.")
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("URL внешнего запроса должен начинаться с http:// или https://.")
    raw_headers = spec.get("headers") or {}
    if not isinstance(raw_headers, dict):
        raise ValueError("Заголовки внешнего запроса должны быть объектом.")
    headers: dict[str, str] = {}
    for key, value in raw_headers.items():
        name = str(key).strip()
        if not name:
            continue
        if any(ch in name for ch in "\r\n:"):
            raise ValueError("Имя заголовка внешнего запроса недопустимо.")
        text = "" if value is None else str(value)
        if any(ch in text for ch in "\r\n"):
            raise ValueError("Значение заголовка внешнего запроса содержит перевод строки.")
        headers[name] = text
    body = spec.get("body", None)
    data: bytes | None = None
    if body not in (None, ""):
        if isinstance(body, (dict, list)):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        else:
            data = str(body).encode("utf-8")
        if len(data) > HTTP_MAX_BYTES:
            raise ValueError("Тело внешнего запроса больше 1 МБ.")
    return method, url, headers, data


def interpret_http_response(status: int, content_type: str, raw: bytes) -> Any:
    """Тело успешного ответа: JSON, если тип или текст похожи на JSON, иначе строка."""
    _http_too_large(raw)
    if status < 200 or status >= 300:
        snippet = raw[:180].decode("utf-8", errors="replace").strip()
        detail = f": {snippet}" if snippet else ""
        raise ValueError(f"Внешний запрос вернул HTTP {status}{detail}")
    text = raw.decode("utf-8", errors="replace")
    kind = content_type.lower()
    looks_json = "json" in kind or (
        "text/" not in kind and "xml" not in kind and "html" not in kind and text.lstrip()[:1] in "{["
    )
    if looks_json and text.strip():
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return text


async def _perform_http_request(
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes | None,
) -> tuple[int, str, bytes]:
    timeout = aiohttp.ClientTimeout(total=20, sock_connect=5)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method,
                url,
                headers=headers,
                data=body,
                allow_redirects=False,
            ) as resp:
                raw = await resp.read()
                _http_too_large(raw)
                return resp.status, resp.headers.get("Content-Type", ""), raw
    except aiohttp.ClientError as ex:
        raise ValueError(f"Внешний запрос не выполнен: {ex}") from ex


async def _resolve_http_request(cfg: dict) -> Any:
    method, url, headers, body = prepare_http_request(cfg.get("httpRequest"))
    status, content_type, raw = await _perform_http_request(method, url, headers, body)
    value = interpret_http_response(status, content_type, raw)
    expr = cfg.get("responseJsonata")
    if isinstance(expr, str) and expr.strip():
        return await evaluate_jsonata(expr.strip(), value)
    return value


async def _resolve_catalog_binding(
    cfg: dict,
    *,
    post_message: Callable[..., Awaitable[Any]],
    initiator_finish: Any,
    virtual_resolution_tag_id: str | None,
    lookup_constant: Callable[[str], Awaitable[Any]] | None,
) -> Any:
    message = validate_binding(cfg)
    if message:
        raise ValueError(message)
    kind = cfg["binding"]
    if kind == "tag":
        request = {"tagId": str(cfg["tagId"]).strip(), "finish": initiator_finish}
        if virtual_resolution_tag_id is not None:
            request["evalContextTagId"] = virtual_resolution_tag_id
        return await post_message(
            mes=request,
            reply=True,
            routing_key="prsTag.app_api_client.data_get.*",
        )
    if kind == "literal":
        return _coerce_literal(cfg.get("value"), as_int(cfg.get("valueTypeCode")) or 0)
    if kind == "constant":
        if lookup_constant is None:
            raise ValueError("Привязка constant недоступна: нет чтения константы.")
        return await lookup_constant(str(cfg["constantId"]).strip())
    raise ValueError("Неизвестный тип привязки параметра.")


async def resolve_parameter_value(
    cfg: dict,
    *,
    post_message: Callable[..., Awaitable[Any]],
    client_request: dict | None,
    initiator_finish: Any,
    initiator_point: list | tuple | None,
    virtual_resolution_tag_id: str | None = None,
    lookup_constant: Callable[[str], Awaitable[Any]] | None = None,
) -> Any:
    """
    initiator_finish — метка времени инициатора (для legacy data_get подставляется в finish).
    initiator_point — сырая точка (x,y,q) при запуске от тега/расписания.

    virtual_resolution_tag_id — id тега-«владельца» виртуального метода: при чтении
    того же тега по legacy ``tagId`` вложенный ``data_get`` не должен снова вызывать
    виртуальный метод (иначе двойной вызов и рекурсия).
    """
    cfg = copy.deepcopy(cfg)
    cfg.pop("clientStub", None)

    if isinstance(cfg.get("binding"), str) and cfg.get("binding").strip():
        if as_int(cfg.get("valueTypeCode")) not in VALUE_TYPE_CODES and cfg.get("binding") == "literal":
            raise ValueError("valueTypeCode привязки должен быть 1, 2, 3 или 4.")
        return await _resolve_catalog_binding(
            cfg,
            post_message=post_message,
            initiator_finish=initiator_finish,
            virtual_resolution_tag_id=virtual_resolution_tag_id,
            lookup_constant=lookup_constant,
        )

    if "httpRequest" in cfg:
        return await _resolve_http_request(cfg)

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

    if "tagId" in cfg:
        request = copy.deepcopy(cfg)
        request["finish"] = initiator_finish
        if virtual_resolution_tag_id is not None:
            request["evalContextTagId"] = virtual_resolution_tag_id
        raw = await post_message(
            mes=request,
            reply=True,
            routing_key="prsTag.app_api_client.data_get.*",
        )
        expr = cfg.get("responseJsonata")
        if isinstance(expr, str) and expr.strip():
            return await evaluate_jsonata(expr.strip(), raw)
        return raw

    ctx: dict = copy.deepcopy(client_request) if isinstance(client_request, dict) else {}
    built_from_initiator = False
    if not ctx and initiator_point is not None:
        p = initiator_point
        ctx = {
            "finish": initiator_finish,
            "start": None,
            "point": {
                "x": p[0],
                "y": p[1] if len(p) > 1 else None,
                "q": p[2] if len(p) > 2 else None,
            },
        }
        built_from_initiator = True

    cj = cfg.get("clientJsonata")
    if isinstance(cj, str) and cj.strip():
        return await evaluate_jsonata(cj.strip(), ctx)

    if isinstance(client_request, dict) or built_from_initiator:
        return ctx

    raise ValueError(
        "Некорректный prsJsonConfigString параметра метода: "
        "нужен httpRequest, routingKey, tagId (legacy GET /v1/data) "
        "или данные клиентского GET /v1/data."
    )
