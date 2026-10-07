import asyncio
from unittest.mock import AsyncMock

from src.services.methods.app.methods_app_svc import MethodsApp
from tests.unit.methods_app_lifecycle_test import _Hierarchy, _make_service


def test_entity_type_and_missing_node_and_routing_key():
    svc = _make_service(_Hierarchy())
    svc._hierarchy.search = AsyncMock(return_value=[])
    assert asyncio.run(svc._method_entity_type("m")) == 0
    svc._hierarchy.search = AsyncMock(return_value=[("m", None, {"prsEntityTypeCode": ["1"]})])
    assert asyncio.run(svc._method_entity_type("m")) == 1
    svc._hierarchy.search = AsyncMock(return_value=[("m", None, {"prsEntityTypeCode": ["bad"]})])
    assert asyncio.run(svc._method_entity_type("m")) == 0
    assert MethodsApp._is_missing_node_error(ValueError("Узел x не найден.")) is True
    assert MethodsApp._is_missing_node_error(RuntimeError("x")) is False
    assert svc._initiator_event_routing_key("prsTag", "t") == "prsTag.app.data_set.t"
    assert svc._initiator_event_routing_key("prsSchedule", "s") == "prsSchedule.app.fire_event.s"
    assert svc._initiator_event_routing_key("prsObject", "o") is None
    assert MethodsApp._unwrap_redis_json_root([["a"]]) == ["a"]
    assert MethodsApp._unwrap_redis_json_root(["a"]) == ["a"]


def test_updated_inactive_and_created():
    svc = _make_service(_Hierarchy())
    svc._handlers = {}
    svc._make_method_cache = AsyncMock()
    svc._delete_method_cache = AsyncMock(return_value=[])
    svc._unbind_unused_initiators = AsyncMock()
    svc._hierarchy.search = AsyncMock(return_value=[("m", None, {"prsActive": ["FALSE"]})])
    asyncio.run(svc._updated({"id": "m"}))
    svc._delete_method_cache.assert_awaited()
    svc._hierarchy.search = AsyncMock(return_value=[])
    asyncio.run(svc._updated({"id": "m"}))
    asyncio.run(svc._created({"id": "m"}))
    svc._make_method_cache.assert_awaited()
    svc._add_app_handlers()
    assert "prsSchedule.app.fire_event.*" in svc._handlers
