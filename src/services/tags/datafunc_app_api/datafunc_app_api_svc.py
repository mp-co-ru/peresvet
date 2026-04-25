"""
Модуль содержит классы, описывающие входные данные для команд CRUD для тегов
и класс сервиса ``tags_api_crud_svc``.
"""
import hashlib
import json
import math
import sys
from typing import Any, cast

import numpy as np
import pandas as pd

from fastapi import APIRouter, Query
from starlette.requests import Request

sys.path.append(".")

from src.common.base_svc import BaseSvc
from src.common.api_crud_svc import valid_uuid
from src.services.tags.datafunc_app_api.datafunc_app_api_settings import DatafuncAppAPISettings
import src.common.times as t
from src.services.tags.app_api.tags_app_api_svc import (
    DataGet,
    _data_get_apply_query_extras,
    _merge_extra_data_get_query_params,
)


def _is_integral_tag_code(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, bool):
        return True
    if isinstance(val, (int, np.integer)):
        return True
    if isinstance(val, (float, np.floating)):
        x = float(val)
        if not math.isfinite(x) or math.isnan(x):
            return False
        return x == math.trunc(x)
    return False


def _integral_code_as_int(val: Any) -> int:
    if isinstance(val, bool):
        return int(val)
    if isinstance(val, (int, np.integer)):
        return int(val)
    return int(float(val))


def _canonical_pair(code: Any) -> tuple:
    if _is_integral_tag_code(code):
        return ("i", _integral_code_as_int(code))
    try:
        dumped = json.dumps(code, sort_keys=True, ensure_ascii=False, default=str)
    except TypeError:
        dumped = f"{type(code).__name__}:{code!r}"
    return ("x", dumped)


def _api_key_for_code(orig: Any) -> Any:
    if isinstance(orig, bool):
        return int(orig)
    if isinstance(orig, (int, np.integer)):
        return int(orig)
    if isinstance(orig, (float, np.floating)):
        x = float(orig)
        if math.isfinite(x) and not math.isnan(x) and x == math.trunc(x):
            return int(x)
    return orig


def _hash_seed_from_cp(cp: tuple) -> int:
    raw = json.dumps(cp, ensure_ascii=False, default=str).encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big", signed=False) % (2**53 - 3) + 1


def build_code_surrogate_maps(
    unique_codes: Any,
) -> tuple[dict[tuple, int], dict[int, Any]]:
    """canonical_pair(code) -> int для pandas; surrogate -> ключ в ответе."""
    ordered = list(dict.fromkeys(x for x in unique_codes if not pd.isna(x)))
    canonical_by_sur: dict[int, tuple] = {}
    cp_to_sur: dict[tuple, int] = {}

    for orig in ordered:
        cp = _canonical_pair(orig)
        if cp[0] != "i":
            continue
        s = int(cp[1])
        canonical_by_sur[s] = cp
        cp_to_sur[cp] = s

    for orig in ordered:
        cp = _canonical_pair(orig)
        if cp[0] == "i":
            continue
        if cp in cp_to_sur:
            continue
        s = _hash_seed_from_cp(cp)
        while s in canonical_by_sur and canonical_by_sur[s] != cp:
            s = (s + 1_300_001) % (2**53 - 3) + 1
        canonical_by_sur[s] = cp
        cp_to_sur[cp] = s

    sur_to_orig: dict[int, Any] = {}
    for orig in ordered:
        cp = _canonical_pair(orig)
        s = cp_to_sur[cp]
        if s not in sur_to_orig:
            sur_to_orig[s] = _api_key_for_code(orig)

    return cp_to_sur, sur_to_orig


def _column_surrogate_codes(series: pd.Series, cp_to_sur: dict[tuple, int]) -> pd.Series:
    return cast(
        pd.Series,
        series.apply(lambda c: cp_to_sur[_canonical_pair(c)]),
    )


def _remap_aggregated_keys(
    by_surrogate: dict[int, int], sur_to_orig: dict[int, Any]
) -> dict:
    return {sur_to_orig[k]: int(v) for k, v in by_surrogate.items()}


class TagsAppAPIDatafunc(BaseSvc):

    def _set_handlers(self):
        self._handlers = {
            f"{self._config.hierarchy['class']}.app_api_client.datafunc_get.*": self.data_get,
        }

    async def data_get(self, mes: DataGet | dict, routing_key: str | None = None) -> dict:
        payload: DataGet
        if isinstance(mes, dict):
            payload = DataGet(**mes)
        else:
            payload = mes
        body = payload.model_dump()
        res = await self._post_message(
            mes=body,
            reply=True,
            routing_key=f"{self._config.hierarchy['class']}.app_api.datafunc_get.*",
        )
        if res is None:
            return {"error": {"code": 424, "message": "Нет обработчика для команды datafunc_get."}}
        if not isinstance(res, dict):
            return {"error": {"code": 500, "message": "Некорректный ответ обработчика datafunc_get."}}
        return res

settings = DatafuncAppAPISettings()

app = TagsAppAPIDatafunc(settings=settings, title="`TagsAppAPIDatafunc` service")

router = APIRouter(prefix=f"{settings.api_version}/datafunc")

@router.get("/", response_model=dict | None, status_code=200)
async def data_get(
    request: Request,
    tagId: list[str] | None = Query(None),
    start: str | None = None,
    finish: str | None = None,
    maxCount: int | None = None,
    format: bool = False,
    actual: bool = False,
    value: str | None = None,
    count: int | None = None,
    timeStep: int | None = None,
    q: str | None = None,
    payload: DataGet | None = None,
):
    if q:
        p = _data_get_apply_query_extras(request, DataGet.model_validate_json(q))
    elif payload:
        p = _data_get_apply_query_extras(request, payload)
    else:
        if not tagId:
            return None
        parsed_value = None
        if value is not None:
            try:
                parsed_value = json.loads(value)
            except Exception:
                parsed_value = value
        body = {"tagId": tagId, "format": format, "actual": actual}
        if start is not None:
            body["start"] = start
        if finish is not None:
            body["finish"] = finish
        if maxCount is not None:
            body["maxCount"] = maxCount
        if parsed_value is not None:
            body["value"] = parsed_value
        if count is not None:
            body["count"] = count
        if timeStep is not None:
            body["timeStep"] = timeStep
        body = _merge_extra_data_get_query_params(request, body)
        p = DataGet.model_validate(body)
    res = await app.data_get(p)
    return res

app.include_router(router, tags=["datafunc"])
