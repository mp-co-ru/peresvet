import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.common.amqp_rpc import NO_AMQP_RPC_REPLY
from src.services.methods.app.methods_app_svc import MethodsApp
from tests.unit.methods_app_lifecycle_test import _Hierarchy, _make_service


def test_virtual_data_get_validates_and_calls_rpc():
    svc = _make_service(_Hierarchy())
    svc._rpc_exchange = SimpleNamespace(call=AsyncMock(return_value=42))
    svc._post_message = AsyncMock(return_value={"ok": True})
    svc._hierarchy.get_parent = AsyncMock(return_value=("tag-1", None))
    svc._method_entity_type = AsyncMock(return_value=1)

    async def search(payload):
        if payload.get("filter", {}).get("objectClass") == ["prsMethodParameter"]:
            return [
                ("p1", None, {"prsJsonConfigString": ["{}"], "prsIndex": ["1"], "cn": ["a"]}),
                ("p2", None, {"prsJsonConfigString": ["{}"], "prsIndex": [None], "cn": ["b"]}),
            ]
        if payload.get("id") == "m1":
            return [("m1", None, {"prsMethodAddress": ["pkg.fn"]})]
        return []

    svc._hierarchy.search = search
    missing = asyncio.run(svc._virtual_data_get({}))
    assert missing["error"]["code"] == 422
    svc._hierarchy.get_parent = AsyncMock(return_value=("other", None))
    assert asyncio.run(svc._virtual_data_get({"methodId": "m1", "tagId": "tag-1"}))["error"]["code"] == 400
    svc._hierarchy.get_parent = AsyncMock(return_value=("tag-1", None))
    svc._method_entity_type = AsyncMock(return_value=0)
    assert asyncio.run(svc._virtual_data_get({"methodId": "m1", "tagId": "tag-1"}))["error"]["code"] == 400
    svc._method_entity_type = AsyncMock(return_value=1)
    ok = asyncio.run(
        svc._virtual_data_get(
            {"methodId": "m1", "tagId": "tag-1", "clientRequest": {"finish": 123}}
        )
    )
    assert ok["data"][0]["tagId"] == "tag-1"
    assert ok["data"][0]["data"][0][1] == 42
    svc._rpc_exchange.call = AsyncMock(side_effect=RuntimeError("boom"))
    err = asyncio.run(
        svc._virtual_data_get({"methodId": "m1", "tagId": "tag-1", "clientRequest": {}})
    )
    assert err["error"]["code"] == 500


def test_virtual_data_get_missing_catalog_does_not_call_copied_address():
    svc = _make_service(_Hierarchy())
    svc._rpc_exchange = SimpleNamespace(call=AsyncMock(return_value=1))
    svc._post_message = AsyncMock(return_value={"ok": True})
    svc._hierarchy.get_parent = AsyncMock(return_value=("tag-1", None))
    svc._hierarchy.get_node_class = AsyncMock(return_value="prsMethod")
    svc._method_entity_type = AsyncMock(return_value=1)

    async def search(payload):
        if payload.get("id") == "m1":
            return [("m1", None, {"prsMethodAddress": ["copied.addr"], "prsCatalogMethodId": ["gone"]})]
        return []

    svc._hierarchy.search = search
    err = asyncio.run(svc._virtual_data_get({"methodId": "m1", "tagId": "tag-1", "clientRequest": {}}))
    assert err["error"]["code"] == 404
    svc._rpc_exchange.call.assert_not_called()


def test_tag_data_get_uses_type_1_method_and_stops_same_tag_recursion():
    svc = _make_service(_Hierarchy())

    async def search(payload):
        if payload.get("base") == "tag-1" and payload.get("filter", {}).get("objectClass") == ["prsMethod"]:
            return [("m1", None, {"prsEntityTypeCode": ["1"], "prsIndex": ["1"], "cn": ["m"]})]
        if payload.get("id") == "m1" and payload.get("attributes") == ["prsEntityTypeCode"]:
            return [("m1", None, {"prsEntityTypeCode": ["1"]})]
        if payload.get("id") == "m1":
            return [("m1", None, {"prsMethodAddress": ["pkg.read"]})]
        return []

    svc._hierarchy.search = search
    svc._hierarchy.get_parent = AsyncMock(return_value=("tag-1", None))
    svc._rpc_exchange = SimpleNamespace(call=AsyncMock(return_value=7))
    svc._post_message = AsyncMock()
    ok = asyncio.run(svc._tag_data_get({"tagId": ["tag-1"], "finish": 5}))
    assert ok["data"][0]["data"][0][1] == 7
    nested = asyncio.run(svc._tag_data_get({"tagId": ["tag-1"], "evalContextTagId": "tag-1"}))
    assert nested["error"]["code"] == 422
    missing = asyncio.run(svc._tag_data_get({"tagId": ["other"]}))
    assert missing is NO_AMQP_RPC_REPLY


def test_read_action_runs_method_and_does_not_reply():
    svc = _make_service(_Hierarchy())

    async def search(payload):
        if payload.get("base") == "tag-1" and payload.get("filter", {}).get("objectClass") == ["prsMethod"]:
            code = payload["attributes"]
            if "prsIndex" in code:
                return [("m3", None, {"prsEntityTypeCode": ["3"], "prsIndex": ["1"], "cn": ["act"]})]
            return []
        if payload.get("id") == "m3" and payload.get("attributes") == ["prsEntityTypeCode"]:
            return [("m3", None, {"prsEntityTypeCode": ["3"]})]
        if payload.get("id") == "m3":
            return [("m3", None, {"prsMethodAddress": ["pkg.act"]})]
        return []

    svc._hierarchy.search = search
    svc._hierarchy.get_parent = AsyncMock(return_value=("tag-1", None))
    svc._rpc_exchange = SimpleNamespace(call=AsyncMock(return_value="done"))
    svc._post_message = AsyncMock()
    res = asyncio.run(svc._tag_data_get({"tagId": ["tag-1"]}))
    assert res is NO_AMQP_RPC_REPLY
    svc._rpc_exchange.call.assert_awaited()


def test_read_action_does_not_replace_type_1_reply():
    svc = _make_service(_Hierarchy())

    async def search(payload):
        attrs = payload.get("attributes") or []
        if payload.get("base") == "tag-1" and payload.get("filter", {}).get("objectClass") == ["prsMethod"]:
            if "prsIndex" in attrs:
                return [
                    ("m1", None, {"prsEntityTypeCode": ["1"], "prsIndex": ["1"], "cn": ["read"]}),
                    ("m3", None, {"prsEntityTypeCode": ["3"], "prsIndex": ["2"], "cn": ["act"]}),
                ]
            return []
        method_id = payload.get("id")
        if method_id == "m1" and attrs == ["prsEntityTypeCode"]:
            return [("m1", None, {"prsEntityTypeCode": ["1"]})]
        if method_id == "m3" and attrs == ["prsEntityTypeCode"]:
            return [("m3", None, {"prsEntityTypeCode": ["3"]})]
        if method_id == "m1":
            return [("m1", None, {"prsMethodAddress": ["pkg.read"]})]
        if method_id == "m3":
            return [("m3", None, {"prsMethodAddress": ["pkg.act"]})]
        return []

    svc._hierarchy.search = search
    svc._hierarchy.get_parent = AsyncMock(return_value=("tag-1", None))
    svc._rpc_exchange = SimpleNamespace(call=AsyncMock(side_effect=["acted", 7]))
    svc._post_message = AsyncMock()
    res = asyncio.run(svc._tag_data_get({"tagId": ["tag-1"], "finish": 5}))
    assert res["data"][0]["data"][0][1] == 7
    assert [call.args[0] for call in svc._rpc_exchange.call.await_args_list] == ["pkg.act", "pkg.read"]


def test_read_action_error_is_not_the_read_reply():
    svc = _make_service(_Hierarchy())

    async def search(payload):
        if payload.get("base") == "tag-1" and "prsIndex" in (payload.get("attributes") or []):
            return [("m3", None, {"prsEntityTypeCode": ["3"], "prsIndex": ["1"], "cn": ["act"]})]
        if payload.get("id") == "m3" and payload.get("attributes") == ["prsEntityTypeCode"]:
            return [("m3", None, {"prsEntityTypeCode": ["3"]})]
        return []

    svc._hierarchy.search = search
    svc._hierarchy.get_parent = AsyncMock(return_value=("tag-1", None))
    svc._rpc_exchange = SimpleNamespace(call=AsyncMock())
    svc._post_message = AsyncMock()
    res = asyncio.run(svc._tag_data_get({"tagId": ["tag-1"]}))
    assert res is NO_AMQP_RPC_REPLY
    assert svc._logger.errors
    svc._rpc_exchange.call.assert_not_called()


def test_write_action_runs_method_and_does_not_reply():
    svc = _make_service(_Hierarchy())

    async def search(payload):
        if payload.get("base") == "tag-1" and payload.get("filter", {}).get("objectClass") == ["prsMethod"]:
            if "prsIndex" in payload.get("attributes", []):
                return [("m4", None, {"prsEntityTypeCode": ["4"], "prsIndex": ["1"], "cn": ["act"]})]
            return []
        if payload.get("id") == "m4" and payload.get("attributes") == ["prsEntityTypeCode"]:
            return [("m4", None, {"prsEntityTypeCode": ["4"]})]
        if payload.get("id") == "m4":
            return [("m4", None, {"prsMethodAddress": ["pkg.act"]})]
        return []

    svc._hierarchy.search = search
    svc._hierarchy.get_parent = AsyncMock(return_value=("tag-1", None))
    svc._rpc_exchange = SimpleNamespace(call=AsyncMock(return_value=None))
    svc._post_message = AsyncMock()
    svc._tag_has_datastorage_tagdata = AsyncMock(return_value=True)
    res = asyncio.run(
        svc._start_method_by_tag({"data": [{"tagId": "tag-1", "data": [[1, 5, 0]]}]})
    )
    assert res is NO_AMQP_RPC_REPLY
    svc._rpc_exchange.call.assert_awaited()


def test_write_action_without_storage_or_writer_acks_with_empty_success():
    svc = _make_service(_Hierarchy())

    async def search(payload):
        if payload.get("base") == "tag-1" and "prsIndex" in (payload.get("attributes") or []):
            return [("m4", None, {"prsEntityTypeCode": ["4"], "prsIndex": ["1"], "cn": ["act"]})]
        if payload.get("id") == "m4" and payload.get("attributes") == ["prsEntityTypeCode"]:
            return [("m4", None, {"prsEntityTypeCode": ["4"]})]
        if payload.get("id") == "m4":
            return [("m4", None, {"prsMethodAddress": ["pkg.onwrite"]})]
        return []

    svc._hierarchy.search = search
    svc._hierarchy.get_parent = AsyncMock(return_value=("tag-1", None))
    svc._rpc_exchange = SimpleNamespace(call=AsyncMock(return_value=None))
    svc._post_message = AsyncMock()
    svc._tag_has_datastorage_tagdata = AsyncMock(return_value=False)
    res = asyncio.run(
        svc._start_method_by_tag({"data": [{"tagId": "tag-1", "data": [[1, 5, 0]]}]})
    )
    assert res == {}
    svc._rpc_exchange.call.assert_awaited()


def test_write_action_does_not_replace_type_2_reply():
    svc = _make_service(_Hierarchy())
    points = [[1, 5, 0]]

    async def search(payload):
        attrs = payload.get("attributes") or []
        if payload.get("base") == "tag-1" and payload.get("filter", {}).get("objectClass") == ["prsMethod"]:
            if "prsIndex" in attrs:
                return [
                    ("m2", None, {"prsEntityTypeCode": ["2"], "prsIndex": ["1"], "cn": ["write"]}),
                    ("m4", None, {"prsEntityTypeCode": ["4"], "prsIndex": ["2"], "cn": ["act"]}),
                ]
            return []
        method_id = payload.get("id")
        if method_id == "m2" and attrs == ["prsEntityTypeCode"]:
            return [("m2", None, {"prsEntityTypeCode": ["2"]})]
        if method_id == "m4" and attrs == ["prsEntityTypeCode"]:
            return [("m4", None, {"prsEntityTypeCode": ["4"]})]
        if method_id == "m2":
            return [("m2", None, {"prsMethodAddress": ["pkg.write"]})]
        if method_id == "m4":
            return [("m4", None, {"prsMethodAddress": ["pkg.onwrite"]})]
        return []

    svc._hierarchy.search = search
    svc._hierarchy.get_parent = AsyncMock(return_value=("tag-1", None))
    svc._rpc_exchange = SimpleNamespace(call=AsyncMock(return_value=None))
    svc._post_message = AsyncMock()
    svc._tag_has_datastorage_tagdata = AsyncMock(return_value=True)
    res = asyncio.run(svc._start_method_by_tag({"data": [{"tagId": "tag-1", "data": points}]}))
    assert res == {}
    assert [call.args[0] for call in svc._rpc_exchange.call.await_args_list] == ["pkg.onwrite", "pkg.write"]
    assert svc._rpc_exchange.call.await_args_list[0].args[-1] == points


def test_tag_writer_calls_method_with_points_last():
    svc = _make_service(_Hierarchy())
    points = [[1, 9, 0]]

    async def search(payload):
        if payload.get("id") == "m2" and payload.get("attributes") == ["prsEntityTypeCode"]:
            return [("m2", None, {"prsEntityTypeCode": ["2"]})]
        if payload.get("id") == "m2":
            return [("m2", None, {"prsMethodAddress": ["pkg.write"]})]
        return []

    svc._hierarchy.search = search
    svc._hierarchy.get_parent = AsyncMock(return_value=("tag-1", None))
    svc._rpc_exchange = SimpleNamespace(call=AsyncMock(return_value=None))
    svc._post_message = AsyncMock()
    ok = asyncio.run(svc._invoke_tag_writer("m2", "tag-1", points))
    assert ok == {}
    assert svc._rpc_exchange.call.await_args.args == ("pkg.write", points)
