import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.methods.app.methods_app_svc import MethodsApp
from tests.unit.methods_app_lifecycle_test import _make_service, _Hierarchy


def _svc():
    svc = _make_service(_Hierarchy())
    svc._rpc_exchange = SimpleNamespace(call=AsyncMock(return_value=3))
    svc._post_message = AsyncMock()
    return svc


def _search(catalog_exists=True, catalog_params=2):
    async def search(payload):
        if payload.get("id") == "inst":
            return [("inst", None, {"prsMethodAddress": ["copied.addr"], "prsCatalogMethodId": ["cat"]})]
        if payload.get("id") == "cat":
            if not catalog_exists:
                return []
            return [("cat", None, {"prsMethodAddress": ["prs.stdlib.add"]})]
        if payload.get("base") == "cat" and payload.get("filter", {}).get("objectClass") == ["prsMethodParameter"]:
            rows = []
            for index in range(1, catalog_params + 1):
                rows.append(
                    (f"c{index}", None, {"prsIndex": [str(index)], "prsValueTypeCode": ["2"], "cn": [f"p{index}"]})
                )
            return rows
        return []

    return search


def _bindings(*values):
    rows = []
    for index, value in enumerate(values, start=1):
        raw = (
            '{"binding":"literal","value":null,"valueTypeCode":2}'
            if value is None
            else '{"binding":"literal","value":%s,"valueTypeCode":2}' % value
        )
        rows.append((f"i{index}", None, {"prsJsonConfigString": [raw], "prsIndex": [str(index)], "cn": [f"p{index}"]}))
    return rows


def test_tag_catalog_method_calls_live_address():
    svc = _svc()
    svc._hierarchy.search = _search()
    svc._hierarchy.get_node_class = AsyncMock(return_value="prsMethod")
    asyncio.run(MethodsApp._calc_tag(svc, "tag-out", "inst", _bindings(1, 2), [10, None, None]))
    svc._rpc_exchange.call.assert_awaited_once()
    assert svc._rpc_exchange.call.await_args.args[0] == "prs.stdlib.add"
    assert svc._rpc_exchange.call.await_args.args[1:] == (1, 2)
    written = svc._post_message.await_args.kwargs["mes"]["data"][0]
    assert written["tagId"] == "tag-out"
    assert written["data"][0][1] == 3


def test_missing_catalog_method_does_not_call_copied_address():
    svc = _svc()
    svc._hierarchy.search = _search(catalog_exists=False)
    svc._hierarchy.get_node_class = AsyncMock(return_value="prsMethod")
    asyncio.run(MethodsApp._calc_tag(svc, "tag-out", "inst", _bindings(1, 2), [10, None, None]))
    svc._rpc_exchange.call.assert_not_called()
    svc._post_message.assert_not_called()


def test_catalog_arity_and_null_do_not_write_tag():
    svc = _svc()
    svc._hierarchy.search = _search(catalog_params=2)
    svc._hierarchy.get_node_class = AsyncMock(return_value="prsMethod")
    asyncio.run(MethodsApp._calc_tag(svc, "tag-out", "inst", _bindings(1), [10, None, None]))
    svc._rpc_exchange.call.assert_not_called()

    svc._rpc_exchange.call.reset_mock()
    with_null = _svc()
    with_null._hierarchy.search = _search()
    with_null._hierarchy.get_node_class = AsyncMock(return_value="prsMethod")
    with pytest.raises(ValueError):
        asyncio.run(MethodsApp._calc_tag(with_null, "tag-out", "inst", _bindings(None, 1), [10, None, None]))
    with_null._rpc_exchange.call.assert_not_called()
    with_null._post_message.assert_not_called()


def test_worker_error_does_not_write_tag():
    svc = _svc()
    svc._rpc_exchange.call = AsyncMock(return_value={"error": "деление на ноль"})
    svc._hierarchy.search = _search()
    svc._hierarchy.get_node_class = AsyncMock(return_value="prsMethod")
    asyncio.run(MethodsApp._calc_tag(svc, "tag-out", "inst", _bindings(1, 0), [10, None, None]))
    svc._post_message.assert_not_called()


def test_virtual_parent_outside_tag_is_ignored():
    from src.services.dataStorages.app.dataStorages_app_base import DataStoragesAppBase

    calls = []

    class Hierarchy:
        def __init__(self, parent_class):
            self.parent_class = parent_class

        async def search(self, payload):
            return [("m1", None, {"prsEntityTypeCode": ["1"], "cn": ["m"]})]

        async def get_parent(self, method_id):
            return "parent", None

        async def get_node_class(self, node_id):
            return self.parent_class

    class Logger:
        def warning(self, *args, **kwargs):
            pass

        def error(self, *args, **kwargs):
            pass

    class _Concrete(DataStoragesAppBase):
        async def _create_store_for_alert(self, *args, **kwargs):
            return None

        async def _create_store_for_tag(self, *args, **kwargs):
            return None

        async def _create_store_name_for_new_alert(self, *args, **kwargs):
            return None

        async def _create_store_name_for_new_tag(self, *args, **kwargs):
            return None

        async def _read_data(self, *args, **kwargs):
            return None

        async def _write_tag_data_to_db(self, *args, **kwargs):
            return None

    svc = object.__new__(_Concrete)
    svc._logger = Logger()

    async def sync(parent):
        calls.append(parent)

    svc._sync_parent_tag_data_get_subscription = sync
    svc._hierarchy = Hierarchy("prsModelNode")
    asyncio.run(DataStoragesAppBase._bind_all_virtual_method_parent_tags(svc))
    assert calls == []
    svc._hierarchy = Hierarchy("prsTag")
    asyncio.run(DataStoragesAppBase._bind_all_virtual_method_parent_tags(svc))
    assert calls == ["parent"]
