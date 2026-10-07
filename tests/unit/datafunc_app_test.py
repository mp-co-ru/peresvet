import asyncio
import math
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import numpy as np
import pandas as pd

from src.services.tags.datafunc_app.datafunc_app_svc import (
    DatafuncApp,
    _api_key_for_code,
    _canonical_pair,
    _column_surrogate_codes,
    _hash_seed_from_cp,
    _integral_code_as_int,
    _is_integral_tag_code,
    _remap_aggregated_keys,
    build_code_surrogate_maps,
)


def test_integral_and_canonical_helpers():
    assert _is_integral_tag_code(None) is False
    assert _is_integral_tag_code(True) is True
    assert _is_integral_tag_code(3) is True
    assert _is_integral_tag_code(np.int64(2)) is True
    assert _is_integral_tag_code(3.0) is True
    assert _is_integral_tag_code(3.5) is False
    assert _is_integral_tag_code(math.nan) is False
    assert _is_integral_tag_code("a") is False
    assert _integral_code_as_int(True) == 1
    assert _integral_code_as_int(np.int64(4)) == 4
    assert _integral_code_as_int(5.0) == 5
    assert _canonical_pair(7) == ("i", 7)
    assert _canonical_pair({"a": 1})[0] == "x"
    assert _api_key_for_code(True) == 1
    assert _api_key_for_code(np.int64(2)) == 2
    assert _api_key_for_code(4.0) == 4
    assert _api_key_for_code("stay") == "stay"
    assert _hash_seed_from_cp(("x", "a")) > 0


def test_build_surrogate_maps_and_remap():
    cp_to_sur, sur_to_orig = build_code_surrogate_maps([1, 1, "on", "on", np.nan])
    assert cp_to_sur[("i", 1)] == 1
    assert sur_to_orig[1] == 1
    str_sur = cp_to_sur[_canonical_pair("on")]
    assert sur_to_orig[str_sur] == "on"
    series = _column_surrogate_codes(pd.Series([1, "on"]), cp_to_sur)
    assert list(series) == [1, str_sur]
    remapped = _remap_aggregated_keys({1: 10, str_sur: 20}, sur_to_orig)
    assert remapped[1] == 10
    assert remapped["on"] == 20


def test_datafunc_data_get_duration_and_errors():
    tid = str(uuid4())
    svc = object.__new__(DatafuncApp)
    svc._config = SimpleNamespace(hierarchy={"class": "prsTag"}, svc_name="datafunc_app")
    svc._logger = SimpleNamespace(debug=lambda *a, **k: None, error=lambda *a, **k: None)
    svc._post_message = AsyncMock(return_value=None)
    svc._handlers = {}
    svc._add_app_handlers()
    assert "prsTag.app_api.datafunc_get.*" in svc._handlers
    err = asyncio.run(svc.data_get({"tagId": tid, "finish": 100}))
    assert err["error"]["code"] == 424
    svc._post_message = AsyncMock(return_value="bad")
    assert asyncio.run(svc.data_get({"tagId": tid, "finish": 100}))["error"]["code"] == 500
    svc._post_message = AsyncMock(return_value={"error": {"code": 500, "message": "x"}})
    assert asyncio.run(svc.data_get({"tagId": tid}))["error"]["code"] == 500

    svc._post_message = AsyncMock(
        return_value={
            "data": [
                {"tagId": tid, "data": []},
                {"tagId": tid, "data": [[10, 1, 0], [20, 1, 0], [30, "on", 0]]},
            ]
        }
    )
    res = asyncio.run(svc.data_get({"tagId": [tid], "finish": 100, "timeStep": None}))
    assert res["data"][0]["data"][0][1] == {}
    assert isinstance(res["data"][1]["data"][0][1], dict)
