import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.services.dataStorages.app.dataStorages_app_base import DataStoragesAppBase, linear_interpolated
from src.services.dataStorages.app.postgresql.dataStorages_app_postgresql_svc import DataStoragesAppPostgreSQL
from src.services.dataStorages.app.victoriametrics.dataStorages_app_victoriametrics_svc import (
    DataStoragesAppVictoriametrics,
)


class _Logger:
    def debug(self, *a, **k):
        pass

    def info(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


class _Queue:
    def __init__(self):
        self.calls = []

    async def bind(self, exchange, routing_key):
        self.calls.append(("bind", routing_key))

    async def unbind(self, exchange, routing_key):
        self.calls.append(("unbind", routing_key))


class _RedisJson:
    def __init__(self, store):
        self.store = store

    async def get(self, key, *paths, **k):
        doc = self.store.get(key)
        if doc is None:
            return None
        if not paths:
            return doc
        if len(paths) == 1:
            if paths[0] == "$":
                return doc
            return doc.get(paths[0]) if isinstance(doc, dict) else doc
        return {p: doc.get(p) for p in paths} if isinstance(doc, dict) else None

    async def set(self, name, path="$", obj=None, nx=False, **k):
        if nx and name in self.store:
            return None
        if path in ("$",):
            self.store[name] = obj
        else:
            self.store.setdefault(name, {})[path.lstrip("$.")] = obj
        return True

    async def delete(self, key):
        self.store.pop(key, None)


class _Redis:
    def __init__(self, store):
        self.store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def json(self):
        return _RedisJson(self.store)


class _DS(DataStoragesAppBase):
    async def _create_store_name_for_new_tag(self, ds_id, tag_id):
        return {"table": f"t_{tag_id}"}

    async def _create_store_for_tag(self, tag_id, ds_id, store):
        pass

    async def _create_store_name_for_new_alert(self, ds_id, alert_id):
        return {"table": f"a_{alert_id}"}

    async def _create_store_for_alert(self, alert_id, ds_id, store):
        pass

    async def _read_data(self, tag_id, start, finish, order, count, one_before, one_after, value=None):
        return list(getattr(self, "_raw", []))

    async def _write_tag_data_to_db(self, tag_id):
        self.flushed = True


def _svc(store=None, ds_type=0, nodes=None):
    svc = object.__new__(_DS)
    svc._config = SimpleNamespace(
        svc_name="dataStorages_app",
        datastorage_type=ds_type,
        nodes=nodes or [],
        datastorages_id=None,
        hierarchy={"class": "prsDataStorage"},
    )
    svc._logger = _Logger()
    svc._cache = SimpleNamespace(get_redis=lambda: _Redis(store if store is not None else {}))
    svc._amqp_consume_queue = _Queue()
    svc._exchange = "ex"
    svc._connection_pools = {"ds-1": object()}
    svc._hierarchy = SimpleNamespace(
        search=AsyncMock(return_value=[]),
        get_node_id=AsyncMock(return_value="ds-root"),
        get_parent=AsyncMock(return_value=("ds-1", None)),
    )
    svc._post_message = AsyncMock(return_value=None)
    svc._handlers = {}
    svc._tags = {}
    return svc


def test_linear_interpolated_and_json_attr_and_ds_type():
    assert linear_interpolated((0, 0), (10, 10), 5) == 5
    assert linear_interpolated((0, "a"), (10, "b"), 5) == "a"
    assert linear_interpolated((0, 3), (10, 3), 5) == 3
    assert linear_interpolated((4, 1), (4, 9), 4) == 1
    svc = _svc()
    assert svc._safe_json_attr(None) is None
    assert svc._safe_json_attr(["{}"]) == {}
    assert svc._safe_json_attr(["  "], default=1) == 1
    assert svc._safe_json_attr(["not"], default=1) == "not"
    assert svc._safe_json_attr([{"a": 1}]) == {"a": 1}
    assert asyncio.run(svc._is_supported_ds_type(0)) is True
    assert asyncio.run(svc._is_supported_ds_type(1)) is False
    assert svc._configured_ds_ids() == []
    svc._config.nodes = ["ds-1", ""]
    assert svc._configured_ds_ids() == ["ds-1"]
    svc._config.nodes = None
    svc._config.datastorages_id = ["legacy"]
    assert svc._configured_ds_ids() == ["legacy"]


def test_timestep_filter_limit_last_point():
    svc = _svc()
    row = svc._timestep_row(10, 5, 0, 100)
    assert row[0] == 0 and row == [0, 10, 20, 30, 40]
    back = svc._timestep_row(10, 3, None, 100)
    assert back == [80, 90, 100]
    data = [(0, 0, None), (10, 10, None), (20, 0, None)]
    crossed = svc._filter_data(data, [5], 1, False)
    assert any(p[1] == 5 for p in crossed)
    stepped = svc._filter_data([(0, 1, None), (1, 2, None)], [2], 0, True)
    assert stepped == [(1, 2, None)]
    json_pts = svc._filter_data([(0, '{"a":1}', None)], [{"a": 1}], 4, True)
    assert json_pts
    assert svc._limit_data([1, 2, 3, 4], 2, start=1, finish=None) == [1, 2]
    assert svc._limit_data([1, 2, 3, 4], 2, start=None, finish=1) == [3, 4]
    assert svc._limit_data([1, 2], 0, 1, 1) == [1, 2]
    assert svc._last_point(10, [(0, 1), (10, 2), (10, 3)]) == (10, 3)


def test_interpolate_numeric_series():
    svc = _svc()
    out = svc._interpolate([(0, 0, None), (10, 10, None)], [0, 5, 10])
    ys = [p[1] for p in out]
    assert 0 in ys or ys[0] == 0
    empty = asyncio.run(svc._data_get_interpolated("t", 0, 10, 2, 10))
    assert all(p[1] is None for p in empty)


def test_bind_tag_alert_ds_and_virtual_read():
    svc = _svc()
    asyncio.run(svc._bind_tag("t1", True))
    asyncio.run(svc._bind_tag("t1", False))
    asyncio.run(svc._bind_alert("a1", True))
    asyncio.run(svc._bind_ds("ds-1", True))
    keys = [c[1] for c in svc._amqp_consume_queue.calls]
    assert "prsTag.app.data_get.t1" in keys
    assert "prsDataStorage.model.link_tag.ds-1" in keys
    none = asyncio.run(svc._read_virtual_method_response("t1", {"evalContextTagId": "t1"}))
    assert none is None
    svc._find_active_virtual_method_id = AsyncMock(return_value="m1")
    svc._post_message = AsyncMock(return_value={"data": [{"tagId": "t1", "data": []}]})
    virt = asyncio.run(svc._read_virtual_method_response("t1", {"tagId": ["t1"]}))
    assert virt["data"][0]["tagId"] == "t1"
    svc._post_message = AsyncMock(return_value=None)
    err = asyncio.run(svc._read_virtual_method_response("t1", {}))
    assert err["error"]["code"] == 424


def test_tag_get_virtual_and_actual():
    store = {"t1.dataStorages_app": {"prsStep": False, "prsValueTypeCode": 1, "data": []}}
    svc = _svc(store=store)
    svc._find_active_virtual_method_id = AsyncMock(return_value="m1")
    svc._post_message = AsyncMock(return_value={"data": [{"tagId": "t1", "data": [[1, 2, 0]]}]})
    svc._write_cache_data = AsyncMock()
    res = asyncio.run(svc._tag_get({
        "tagId": ["t1"],
        "start": 0,
        "finish": 10,
        "maxCount": None,
        "format": False,
        "actual": False,
        "value": None,
        "count": None,
        "timeStep": None,
    }))
    assert res["data"][0]["data"][0][1] == 2

    svc2 = _svc(store=store)
    svc2._find_active_virtual_method_id = AsyncMock(return_value=None)
    svc2._write_cache_data = AsyncMock()
    svc2._raw = [(5, 9, 0)]
    actual = asyncio.run(svc2._tag_get({
        "tagId": ["t1"],
        "start": 0,
        "finish": 10,
        "maxCount": 1,
        "format": False,
        "actual": True,
        "value": None,
        "count": 1,
        "timeStep": None,
    }))
    assert actual["data"][0]["excess"] is False


def test_data_get_one_many_and_reject():
    store = {"t1.dataStorages_app": {"prsStep": False, "prsValueTypeCode": 0}}
    svc = _svc(store=store)
    svc._raw = [(0, 0, 0), (10, 10, 0)]
    one = asyncio.run(svc._data_get_one("t1", 5))
    assert one[0][0] == 5
    many = asyncio.run(svc._data_get_many("t1", 0, 10, None))
    assert many[0][0] == 0
    missing = _svc(store={})
    assert asyncio.run(missing._data_get_one("t1", 1)) == []
    assert asyncio.run(svc._reject_message({"action": "x"})) is False
    info = asyncio.run(svc._get_ds_info("ds-1"))
    assert info is None
    svc._hierarchy.search = AsyncMock(return_value=[
        ("ds-1", None, {"prsEntityTypeCode": ["0"], "prsJsonConfigString": ["{}"], "prsActive": ["TRUE"]})
    ])
    info = asyncio.run(svc._get_ds_info("ds-1"))
    assert info["type"] == 0
    asyncio.run(svc._await_close_pool(None))

    class Pool:
        async def close(self):
            self.closed = True

    asyncio.run(svc._await_close_pool(Pool()))
    asyncio.run(svc._delete_tag_cache("t1"))
    cache = asyncio.run(svc._create_alert_cache("a1"))
    assert "dss" in cache
    svc._add_app_handlers()
    assert "prsTag.app.data_get.*" in svc._handlers


def test_postgresql_and_victoria_sql_filters():
    pg = object.__new__(DataStoragesAppPostgreSQL)
    assert asyncio.run(pg._create_store_name_for_new_tag("ds", "tag")) == {"table": "t_tag"}
    assert asyncio.run(pg._check_store_name_for_new_tag("ds", {"table": "t"})) is True
    assert asyncio.run(pg._check_store_name_for_new_tag("ds", {})) is False
    cond, adapted = pg._get_values_filter(None)
    assert cond == ""
    cond, adapted = pg._get_values_filter(5)
    assert '="y" = $1' in cond.replace(" ", "") or '"y" = $1' in cond
    cond, adapted = pg._get_values_filter({"a": 1})
    assert "@>" in cond
    cond, adapted = pg._get_values_filter([1, None, 2])
    assert "IS NULL" in cond
    cond, adapted = pg._get_values_filter([{"a": 1}, {"b": 2}])
    assert "@>" in cond
    assert pg._limit_data(list(range(5)), 2, start=1, finish=None) == [0, 1]
    vm = object.__new__(DataStoragesAppVictoriametrics)
    assert vm._get_values_filter(None)[0] == ""
    assert '"y" = $1' in vm._get_values_filter(3)[0]


def test_numeric_value_filter_is_not_measured_with_len():
    assert DataStoragesAppBase._has_value_filter(1) is True
    assert DataStoragesAppBase._has_value_filter(0) is True
    assert DataStoragesAppBase._has_value_filter(1.5) is True
    assert DataStoragesAppBase._has_value_filter(True) is True
    assert DataStoragesAppBase._has_value_filter(False) is True
    assert DataStoragesAppBase._has_value_filter(None) is False
    assert DataStoragesAppBase._has_value_filter("") is False
    assert DataStoragesAppBase._has_value_filter([]) is False
    assert DataStoragesAppBase._has_value_filter({}) is False

    pg = object.__new__(DataStoragesAppPostgreSQL)
    points = [(1, 1, 0), (2, 2, 0)]
    assert pg._filter_data(points, 1, 1, True) == [(1, 1, 0)]
    assert DataStoragesAppBase.coerce_filter_value(1, 2) == "1"
    assert DataStoragesAppBase.coerce_filter_value("1", 2) == "1"
    assert DataStoragesAppBase.coerce_filter_value([1, 2], 2) == ["1", "2"]
    assert DataStoragesAppBase.coerce_filter_value(1, 0) == 1
    assert DataStoragesAppBase.coerce_filter_value("2", 0) == 2
    assert DataStoragesAppBase.coerce_filter_value(1, 1) == 1.0
    assert DataStoragesAppBase.coerce_filter_value(None, 2) is None
    points = [(1, "1", 0), (2, "2", 0)]
    assert pg._filter_data(points, 1, 2, True) == [(1, "1", 0)]
    cond, adapted = pg._get_values_filter(DataStoragesAppBase.coerce_filter_value(1, 2))
    assert adapted == ["1"]
    pg._tags = {"t1": {"value_type": 0, "step": False}}
    meta = asyncio.run(pg._tag_value_filter_meta("t1"))
    assert meta == {"value_type": 0, "step": False}
