import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

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
