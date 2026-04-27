import hashlib
import json
import math
import sys
from typing import Any, cast

import numpy as np
import pandas as pd

sys.path.append(".")

from src.common.app_svc import AppSvc
from src.services.tags.app_api.tags_app_api_svc import DataGet
from src.services.tags.datafunc_app.datafunc_app_settings import DatafuncAppSettings
import src.common.times as t


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


class DatafuncApp(AppSvc):
    def _add_app_handlers(self):
        self._handlers[f"{self._config.hierarchy['class']}.app_api.datafunc_get.*"] = self.data_get

    async def data_get(self, mes: DataGet | dict, routing_key: str | None = None) -> dict:
        payload: DataGet
        if isinstance(mes, dict):
            payload = DataGet(**mes)
        else:
            payload = mes
        payload = payload.model_copy(deep=True)

        final_ts = t.ts(payload.finish)
        format_ts = payload.format
        current_ts = t.int_to_local_timestamp(t.now_int())
        if format_ts:
            final_ts = t.int_to_local_timestamp(final_ts)
            payload.format = False

        time_step = payload.timeStep
        if time_step:
            payload.timeStep = None

        res = await self._post_message(
            mes=payload.model_dump(),
            reply=True,
            routing_key=f"{self._config.hierarchy['class']}.app_api.data_get.*",
        )
        if res is None:
            return {"error": {"code": 424, "message": "Нет обработчика для команды чтения данных."}}
        if not isinstance(res, dict):
            return {"error": {"code": 500, "message": "Некорректный ответ обработчика data_get."}}
        if "error" in res:
            return res

        final_res = {"data": []}

        if not time_step:
            for tag in res["data"]:
                df = pd.DataFrame(tag["data"], columns=["ts", "code", "q"])
                df = df.drop("q", axis=1).dropna(subset=["ts", "code"])
                if df.empty:
                    final_res["data"].append(
                        {"tagId": tag["tagId"], "data": [(final_ts, {}, None)]}
                    )
                    continue
                cp_to_sur, sur_to_orig = build_code_surrogate_maps(df["code"].unique())
                df["code"] = _column_surrogate_codes(cast(pd.Series, df["code"]), cp_to_sur)
                df["ts"] = df["ts"].astype(int)

                df["duration"] = df["ts"].diff(periods=-1).fillna(0)
                df["duration"] = df["duration"] * (-1)
                df = df.groupby("code")["duration"].sum()

                df = df.astype(int)
                final_value = _remap_aggregated_keys(df.to_dict(), sur_to_orig)
                final_res["data"].append(
                    {"tagId": tag["tagId"], "data": [(final_ts, final_value, None)]}
                )
        else:
            for tag in res["data"]:
                data = tag["data"]
                final_data = []
                if data:
                    df = pd.DataFrame(data=data, columns=["ts", "code", "q"])
                    df = df.drop("q", axis=1).dropna(subset=["ts", "code"])
                    if df.empty:
                        final_res["data"].append({"tagId": tag["tagId"], "data": []})
                        continue
                    cp_to_sur, sur_to_orig = build_code_surrogate_maps(df["code"].unique())
                    df["code"] = _column_surrogate_codes(cast(pd.Series, df["code"]), cp_to_sur)
                    df["date"] = df["ts"].apply(t.int_to_local_timestamp)

                    response_code_keys = list(dict.fromkeys(sur_to_orig.values()))
                    df = df.set_index("date")
                    rs = df.resample(f"{time_step}us", label="right")

                    prev_y = None
                    prev_x = None
                    prev_ts = None
                    item_count = len(rs) - 1
                    i = 0
                    for x, y in rs:
                        x2 = (x, current_ts)[i == item_count]
                        i += 1

                        y = y.dropna()
                        y["ts"] = y["ts"].astype(np.int64)
                        y["code"] = y["code"].astype(np.int64)
                        last_ts = int((x2 - t.start_ts).total_seconds() * t.microsec)
                        if not len(y.index):
                            if prev_y is None:
                                continue
                            y = pd.DataFrame({"code": prev_y, "ts": prev_ts}, index=[prev_x])

                        last_y = int(y["code"].iloc[-1])
                        if prev_x:
                            y = pd.concat(
                                [y, pd.DataFrame({"code": prev_y, "ts": prev_ts}, index=[prev_x])]
                            )
                        y = pd.concat([y, pd.DataFrame({"code": last_y, "ts": last_ts}, index=[x])])
                        prev_x = x
                        prev_y = last_y
                        prev_ts = last_ts
                        y.sort_index(inplace=True)

                        y["duration"] = y["ts"].diff(periods=-1).fillna(0)
                        y["duration"] = (y["duration"] * (-1)).astype(int)
                        y = y.groupby("code")["duration"].sum()
                        y = y.astype(int)
                        value = _remap_aggregated_keys(y.to_dict(), sur_to_orig)

                        for state in response_code_keys:
                            value.setdefault(state, 0)

                        if format_ts:
                            last_ts = t.int_to_local_timestamp(last_ts)
                        final_data.append((x, value, None))

                final_res["data"].append({"tagId": tag["tagId"], "data": final_data})

        return final_res


settings = DatafuncAppSettings()
app = DatafuncApp(settings=settings, title="`DatafuncApp` service")
