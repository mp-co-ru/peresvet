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

sys.path.append(".")

from src.common import svc
from src.common.api_crud_svc import valid_uuid
from src.services.tags.datafunc_app_api.datafunc_app_api_settings import DatafuncAppAPISettings
import src.common.times as t
from src.services.tags.app_api.tags_app_api_svc import TagsAppAPI, DataGet


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


class TagsAppAPIDatafunc(TagsAppAPI):

    def _set_handlers(self):
        self._handlers = {
        }

    async def data_get(self, mes: DataGet, routing_key: str = None) -> dict:
        """Метод применяет к обычному результату data/get обработку pandas
        с целью высчитать накопительное значение времени по кодам.
        Код состояния (``code``) может быть целым или произвольным значением;
        для расчёта нецелочисленные коды заменяются на устойчивый int-суррогат,
        в ответе снова используются исходные значения.

        Возвращаемые родительским data/get'ом данные по одному тегу должны быть
        вида:
        [
            [<code>, <ts>]
            [<code>, <ts>]...
        ]

        Args:
            payload (DataGet): обычный вход для data/get

        Returns:
            dict: {
                "data": [
                    {
                        "tagId": "...",
                        "data": [
                            [{"<code>": <накопительное значение микросекунд>}, x]
                        ]
                    }

                ]
            }
        """
        final_ts = mes.finish
        format_ts = mes.format
        current_ts = t.int_to_local_timestamp(t.now_int())
        if format_ts:
            # если изначальный запрос с флагом format = true,
            # то удалим его и отформатируем время уже в конце
            final_ts = t.int_to_local_timestamp(final_ts)
            mes.format = False

        timeStep = mes.timeStep
        if timeStep:
            mes.timeStep = None

        res = await super().data_get(mes=mes)
        if 'error' in res.keys():
            return res

        final_res = {
            "data": []
        }

        # для скорости не оптимизируем код, просто добавляем случай, когда
        # есть timeStep
        #TODO: оптимизировать код
        if not timeStep:
            for tag in res["data"]:
                df = pd.DataFrame(tag["data"], columns=['ts', 'code', 'q'])
                df = df.drop('q', axis=1).dropna(subset=['ts', 'code'])
                if df.empty:
                    final_res['data'].append({
                        "tagId": tag["tagId"],
                        "data": [(final_ts, {}, None)],
                    })
                    continue
                cp_to_sur, sur_to_orig = build_code_surrogate_maps(df['code'].unique())
                df['code'] = _column_surrogate_codes(cast(pd.Series, df['code']), cp_to_sur)
                df['ts'] = df['ts'].astype(int)

                df['duration'] = df['ts'].diff(periods=-1).fillna(0)
                df['duration'] = df['duration'] * (-1)
                df = df.groupby('code')['duration'].sum()

                df = df.astype(int)

                final_value = _remap_aggregated_keys(df.to_dict(), sur_to_orig)

                final_res['data'].append({
                    "tagId": tag["tagId"],
                    "data": [
                        (final_ts, final_value, None)
                    ]
                })

        else:

            for tag in res["data"]:
                data = tag["data"]
                final_data = []
                if data:
                    df = pd.DataFrame(data=data,columns=["ts", "code", "q"])
                    df = df.drop('q', axis=1).dropna(subset=['ts', 'code'])
                    if df.empty:
                        final_res['data'].append({
                            "tagId": tag["tagId"],
                            "data": [],
                        })
                        continue
                    cp_to_sur, sur_to_orig = build_code_surrogate_maps(df['code'].unique())
                    df['code'] = _column_surrogate_codes(cast(pd.Series, df['code']), cp_to_sur)
                    df['date'] = df['ts'].apply(t.int_to_local_timestamp)

                    response_code_keys = list(dict.fromkeys(sur_to_orig.values()))
                    df = df.set_index("date")
                    rs = df.resample(f'{timeStep}us', label='right')

                    prev_y = None
                    prev_x = None
                    prev_ts = None
                    item_count = len(rs) - 1
                    i = 0
                    for x, y in rs:
                        x2 = (x, current_ts)[i == item_count]
                        i += 1

                        y = y.dropna()
                        y['ts'] = y['ts'].astype(np.int64)
                        y['code'] = y['code'].astype(np.int64)
                        last_ts = int((x2 - t.start_ts).total_seconds() * t.microsec)
                        if not len(y.index):
                            if prev_y is None:
                                continue
                            y = pd.DataFrame({"code": prev_y, "ts": prev_ts}, index=[prev_x])

                        last_y = int(y["code"].iloc[-1])
                        if prev_x:
                            y = pd.concat([y, pd.DataFrame({"code": prev_y, "ts": prev_ts}, index=[prev_x])])
                        y = pd.concat([y, pd.DataFrame({"code": last_y, "ts": last_ts}, index=[x])])
                        prev_x = x
                        prev_y = last_y
                        prev_ts = last_ts
                        y.sort_index(inplace=True)

                        y['duration'] = y['ts'].diff(periods=-1).fillna(0)
                        y['duration'] = (y['duration'] * (-1)).astype(int)
                        y = y.groupby('code')['duration'].sum()
                        y = y.astype(int)
                        value = _remap_aggregated_keys(y.to_dict(), sur_to_orig)

                        for state in response_code_keys:
                            value.setdefault(state, 0)

                        if format_ts:
                            last_ts = t.int_to_local_timestamp(last_ts)
                        final_data.append((x, value, None))

                final_res['data'].append({
                    "tagId": tag["tagId"],
                    "data": final_data
                })

        return final_res

settings = DatafuncAppAPISettings()

app = TagsAppAPIDatafunc(settings=settings, title="`TagsAppAPIDatafunc` service")

router = APIRouter(prefix=f"{settings.api_version}/datafunc")

@router.get("/", response_model=dict | None, status_code=200)
async def data_get(
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
        p = DataGet.model_validate_json(q)
    elif payload:
        p = payload
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
        p = DataGet.model_validate(body)
    res = await app.data_get(p)
    return res

app.include_router(router, tags=["datafunc"])
