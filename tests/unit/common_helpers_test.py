import asyncio
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.common import times
from src.common.consts import CNDataStorageTypes, CNHTTPExceptionCodes, CNTagValueTypes, Order
from src.common.json_rpc_sanitize import sanitize_for_json_rpc, to_redis_json_scalar
from src.common.runtime_flags import platform_shutting_down, set_platform_shutting_down
from src.common.tag_data_points import (
    coerce_tag_data_items_for_data_set,
    normalize_point_xyq,
    tag_data_points_json_safe,
)
from src.common.tag_quality_codes import (
    CN_QUALITY_CONNECTION_LOST,
    CN_QUALITY_CONNECTION_RESTORED,
    CN_QUALITY_GOOD,
)
from src.common.virtual_method_lookup import find_active_virtual_method_id


def test_times_int_and_digit_strings():
    assert times.ts(1776438870185000) == 1776438870185000
    assert times.ts("1776438870185000") == 1776438870185000
    assert times.ts("+12") == 12
    assert times.ts("-3") == -3
    assert times._int_str_as_microseconds("") is None
    assert times._int_str_as_microseconds("12.5") is None
    now = times.ts(None)
    assert isinstance(now, int) and now > 0


def test_times_iso_and_local_format():
    micros = times.ts("1970-01-01T00:00:01Z")
    assert micros == 1_000_000
    naive = times.ts("1970-01-01T00:00:01")
    assert naive == 1_000_000
    assert times.ts_to_local_str(None) is None
    assert times.ts_to_local_str("keep") == "keep"
    local = times.ts_to_local_str(1_000_000)
    assert isinstance(local, str) and "1970" in local
    assert times.int_to_local_timestamp(None) is None
    dt = times.int_to_local_timestamp(1_000_000)
    assert dt.year == 1970


def test_sanitize_and_redis_scalar_cover_python_and_numpy_like():
    class Item:
        def item(self):
            return Decimal("2.5")

    class BadItem:
        def item(self):
            raise RuntimeError("nope")

    payload = {
        "t": (1, Decimal("1.5"), b"ok"),
        "s": {1, 2},
        "d": datetime(1970, 1, 1),
        "day": date(1970, 1, 2),
        "n": None,
        "b": True,
        "item": Item(),
    }
    out = sanitize_for_json_rpc(payload)
    assert out["t"] == [1, 1.5, "ok"]
    assert sorted(out["s"]) == [1, 2]
    assert out["d"].startswith("1970-01-01")
    assert out["day"] == "1970-01-02"
    assert out["item"] == 2.5
    assert sanitize_for_json_rpc(BadItem()) is not None
    assert to_redis_json_scalar(Decimal("3")) == 3.0
    assert to_redis_json_scalar(b"x") == "x"
    assert to_redis_json_scalar(Item()) == 2.5
    assert to_redis_json_scalar(object()) is not None


def test_tag_data_points_normalization():
    empty = normalize_point_xyq(None)
    assert empty[1] is None and empty[2] is None
    one = normalize_point_xyq([42])
    assert one[1] == 42 and one[2] is None
    two = normalize_point_xyq([1, "y"])
    assert two == (1, "y", None)
    three = normalize_point_xyq([2, "y", 100])
    assert three == (2, "y", 100)
    assert normalize_point_xyq([])[1] is None
    assert normalize_point_xyq("keep") == "keep"
    assert normalize_point_xyq({"a": 1}) == {"a": 1}
    assert normalize_point_xyq(7) == 7
    assert normalize_point_xyq([1, 2, 3, 4]) == [1, 2, 3, 4]
    assert coerce_tag_data_items_for_data_set(None) == []
    assert coerce_tag_data_items_for_data_set((1, 2)) == [(1, 2)]
    assert coerce_tag_data_items_for_data_set([10, 20]) == [[10, 20]]
    assert coerce_tag_data_items_for_data_set([[1, 2], [3, 4]]) == [[1, 2], [3, 4]]
    assert coerce_tag_data_items_for_data_set("x") == ["x"]
    assert tag_data_points_json_safe([(1, 2, 3), [4, 5]]) == [[1, 2, 3], [4, 5]]


def test_consts_and_quality_and_runtime_flag():
    assert CN_QUALITY_GOOD == 0
    assert CN_QUALITY_CONNECTION_LOST == 100
    assert CN_QUALITY_CONNECTION_RESTORED == 101
    assert CNDataStorageTypes.CN_DS_INTEGRATIONAL_POSTGRESQL == 2
    assert CNDataStorageTypes.CN_DS_POSTGRESQL in CNDataStorageTypes.get_supported()
    assert CNHTTPExceptionCodes.CN_424 == 424
    assert CNTagValueTypes.CN_TABLE == 5
    assert Order.CN_DESC == 2
    prev = platform_shutting_down
    try:
        set_platform_shutting_down(True)
        from src.common import runtime_flags
        assert runtime_flags.platform_shutting_down is True
    finally:
        set_platform_shutting_down(prev)


def test_virtual_method_lookup_picks_lowest_index():
    hierarchy = SimpleNamespace()

    async def search(payload):
        assert payload["filter"]["objectClass"] == ["prsMethod"]
        return [
            ("m-plain", None, {"prsEntityTypeCode": ["0"], "prsIndex": ["1"]}),
            ("m-bad", None, {"prsEntityTypeCode": ["x"], "prsIndex": ["0"]}),
            ("m-virt-2", None, {"prsEntityTypeCode": ["1"], "prsIndex": ["5"]}),
            ("m-virt-1", None, {"prsEntityTypeCode": ["1"], "prsIndex": ["2"]}),
            ("m-virt-none", None, {"prsEntityTypeCode": ["1"], "prsIndex": [None]}),
        ]

    hierarchy.search = search
    assert asyncio.run(find_active_virtual_method_id(hierarchy, "tag-1")) == "m-virt-1"
    hierarchy.search = AsyncMock(return_value=[])
    assert asyncio.run(find_active_virtual_method_id(hierarchy, "tag-1")) is None
    hierarchy.search = AsyncMock(
        return_value=[("m", None, {"prsEntityTypeCode": ["0"], "prsIndex": ["1"]})]
    )
    assert asyncio.run(find_active_virtual_method_id(hierarchy, "tag-1")) is None


def test_jsonata_group_data_index_tail():
    from src.common.jsonata_eval import _jsonatapy_group_data_index_tail

    assert _jsonatapy_group_data_index_tail("data[0].data[0][1]") == "(data[0].data)[0][1]"
    assert _jsonatapy_group_data_index_tail("$.data[0].data[1]") == "$.(data[0].data)[1]"
    assert _jsonatapy_group_data_index_tail("plain") is None
    assert _jsonatapy_group_data_index_tail(" (data[0].data)[0] ") is None


def test_evaluate_jsonata_retries_grouped_path():
    from src.common import jsonata_eval

    calls = []

    def evaluate(expr, data):
        calls.append(expr)
        if expr.startswith("(") or ".(" in expr:
            return 7
        return None

    with patch.dict("sys.modules", {"jsonatapy": SimpleNamespace(evaluate=evaluate)}):
        result = asyncio.run(jsonata_eval.evaluate_jsonata("data[0].data[0]", {"x": 1}))
    assert result == 7
    assert calls[0] == "data[0].data[0]"


def test_evaluate_jsonata_timeout_and_missing_module():
    from src.common import jsonata_eval

    with patch.dict("sys.modules", {"jsonatapy": None}):
        with pytest.raises(ModuleNotFoundError):
            asyncio.run(jsonata_eval.evaluate_jsonata("1", {}))

    def evaluate(expr, data):
        return 1

    with patch.dict("sys.modules", {"jsonatapy": SimpleNamespace(evaluate=evaluate)}):
        assert asyncio.run(jsonata_eval.evaluate_jsonata("1", {}, timeout_ms=1000)) == 1


def test_cache_get_set_with_mocked_ldap():
    from src.common.cache import Cache

    cache = Cache.__new__(Cache)
    cache._base_dn = "cn=prs"
    cache._cache_node_dn = "cn=_cache,cn=prs"

    class Conn:
        def __init__(self):
            self.added = None
            self.modified = None

        def search_s(self, **kwargs):
            if kwargs.get("base", "").startswith("cn=missing"):
                raise Exception("nope")
            if "prsJsonConfigString" in kwargs.get("attrlist", []):
                return [("cn=k,cn=_cache,cn=prs", {"prsJsonConfigString": [b'{"a":1}']})]
            return []

        def add_s(self, dn, modlist):
            self.added = (dn, modlist)
            raise __import__("ldap").ALREADY_EXISTS()

        def modify_s(self, dn, modlist):
            self.modified = (dn, modlist)

    conn = Conn()

    class CM:
        def connection(self):
            class Ctx:
                def __enter__(self_inner):
                    return conn

                def __exit__(self_inner, *a):
                    return False

            return Ctx()

    cache._cm = CM()
    assert asyncio.run(cache.get_key("missing")) is None
    assert asyncio.run(cache.get_key("k")) == '{"a":1}'
    assert asyncio.run(cache.get_key("k", json_loads=True)) == {"a": 1}

    asyncio.run(cache.set_key("k", {"b": 2}))
    assert conn.modified is not None

    conn.add_s = lambda dn, modlist: setattr(conn, "added", (dn, modlist))
    asyncio.run(cache.set_key("k2", "plain"))
    assert conn.added[0].startswith("cn=")


def test_redis_cache_pipelines_commands():
    from src.common.redis_cache import RedisCache

    class Pipe:
        def __init__(self):
            self.ops = []

        def json(self):
            return self

        def set(self, *a, **k):
            self.ops.append(("set", a, k))

        def get(self, *a, **k):
            self.ops.append(("get", a, k))

        def delete(self, *a, **k):
            self.ops.append(("delete", a, k))

        def arrappend(self, *a, **k):
            self.ops.append(("append", a, k))

        def arrindex(self, *a, **k):
            self.ops.append(("index", a, k))

        def arrpop(self, *a, **k):
            self.ops.append(("pop", a, k))

        async def execute(self):
            return ["ok"]

        async def reset(self):
            self.ops.append("reset")

    class Client:
        def __init__(self):
            self.pipe = Pipe()

        def pipeline(self, transaction=True):
            return self.pipe

        async def aclose(self):
            self.closed = True

    rc = RedisCache.__new__(RedisCache)
    rc._pool = object()
    rc._client = None
    rc._pipe = None
    client = Client()
    with patch("src.common.redis_cache.redis.Redis", return_value=client):
        with patch("src.common.redis_cache.redis.Redis.from_pool", return_value=client):
            assert rc.set("n", "$", {"a": 1}) is rc
            assert rc.get("n", "a") is rc
            assert rc.delete("n", "a") is rc
            assert rc.append("n", "arr", 1) is rc
            assert rc.index("n", "arr", 1) is rc
            assert rc.pop("n", "arr", 0) is rc
            assert asyncio.run(rc.exec()) == ["ok"]
            rc._client = client
            rc._pipe = client.pipe
            asyncio.run(rc.reset())
            asyncio.run(rc.close())
