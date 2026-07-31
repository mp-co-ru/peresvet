import asyncio
import types

from src.services.methods.app.methods_app_svc import MethodsApp


class _Logger:
    def debug(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


class _Queue:
    def __init__(self):
        self.calls = []

    async def bind(self, exchange, routing_key):
        self.calls.append(("bind", exchange, routing_key))

    async def unbind(self, exchange, routing_key):
        self.calls.append(("unbind", exchange, routing_key))


class _RedisJson:
    def __init__(self, store):
        self.store = store

    async def get(self, key, *args, **kwargs):
        return self.store.get(key)

    async def set(self, name, path, obj):
        if path == "$":
            self.store[name] = obj
        else:
            self.store.setdefault(name, {})[path] = obj

    async def delete(self, key, path=None):
        if path is None:
            self.store.pop(key, None)
            return
        value = self.store.get(key)
        if isinstance(value, dict):
            value.pop(path, None)


class _Redis:
    def __init__(self, store):
        self.store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def json(self):
        return _RedisJson(self.store)


class _Cache:
    def __init__(self):
        self.store = {}

    def get_redis(self):
        return _Redis(self.store)


class _Hierarchy:
    def __init__(
        self,
        *,
        method_ids=None,
        method_type=0,
        initiators=None,
        initiator_classes=None,
        parent_tag_id="result-tag",
    ):
        self.method_ids = method_ids or ["method-1"]
        self.method_type = method_type
        self.initiators = initiators or []
        self.initiator_classes = initiator_classes or {}
        self.parent_tag_id = parent_tag_id

    async def search(self, payload):
        if payload.get("filter") == {"objectClass": ["prsMethod"], "prsActive": ["TRUE"]}:
            return [(method_id, None, {"cn": [method_id]}) for method_id in self.method_ids]
        if payload.get("id") and payload.get("attributes") == ["prsEntityTypeCode"]:
            return [(payload["id"], None, {"prsEntityTypeCode": [str(self.method_type)]})]
        if str(payload.get("base", "")).startswith("cn=initiatedBy,cn=system,"):
            return [
                (initiator_id, None, {"cn": [initiator_id]})
                for initiator_id in self.initiators
            ]
        return []

    async def get_node_dn(self, method_id):
        return f"cn={method_id},cn=methods,cn=prs"

    async def get_node_class(self, node_id):
        return self.initiator_classes.get(node_id, "prsTag")

    async def get_parent(self, method_id):
        return self.parent_tag_id, None


def _make_service(hierarchy):
    svc = object.__new__(MethodsApp)
    svc._hierarchy = hierarchy
    svc._cache = _Cache()
    svc._amqp_consume_queue = _Queue()
    svc._exchange = "main"
    svc._config = types.SimpleNamespace(svc_name="methods_app")
    svc._logger = _Logger()
    return svc


def test_make_method_cache_rebinds_active_tag_initiator_after_unbind():
    svc = _make_service(_Hierarchy(initiators=["initiator-tag"]))

    ok = asyncio.run(MethodsApp._make_method_cache(svc, "method-1"))

    assert ok is True
    assert svc._amqp_consume_queue.calls == [
        ("unbind", "main", "prsTag.app.data_set.initiator-tag"),
        ("bind", "main", "prsTag.app.data_set.initiator-tag"),
    ]
    assert svc._cache.store["initiator-tag.methods_app"] == {"method-1": "result-tag"}
    assert svc._cache.store["method-1.methods_app"] == ["initiator-tag"]


def test_make_method_cache_rebinds_active_schedule_initiator_after_unbind():
    svc = _make_service(
        _Hierarchy(
            initiators=["initiator-schedule"],
            initiator_classes={"initiator-schedule": "prsSchedule"},
        )
    )

    ok = asyncio.run(MethodsApp._make_method_cache(svc, "method-1"))

    assert ok is True
    assert svc._amqp_consume_queue.calls == [
        ("unbind", "main", "prsSchedule.app.fire_event.initiator-schedule"),
        ("bind", "main", "prsSchedule.app.fire_event.initiator-schedule"),
    ]
    assert svc._cache.store["initiator-schedule.methods_app"] == {"method-1": "result-tag"}
    assert svc._cache.store["method-1.methods_app"] == ["initiator-schedule"]


def test_make_method_cache_does_not_rebind_without_initiators():
    svc = _make_service(_Hierarchy(initiators=[]))

    ok = asyncio.run(MethodsApp._make_method_cache(svc, "method-1"))

    assert ok is False
    assert all(call[0] != "bind" for call in svc._amqp_consume_queue.calls)
    assert svc._cache.store == {}


def test_make_method_cache_does_not_build_initiator_cache_for_virtual_method():
    svc = _make_service(_Hierarchy(method_type=1, initiators=["initiator-tag"]))

    ok = asyncio.run(MethodsApp._make_method_cache(svc, "method-1"))

    assert ok is True
    assert svc._amqp_consume_queue.calls == [
        ("unbind", "main", "prsTag.app.data_set.initiator-tag"),
    ]
    assert svc._cache.store == {}


def test_get_methods_does_not_bind_twice_after_cache_rebuild():
    svc = _make_service(_Hierarchy(initiators=["initiator-tag"]))

    asyncio.run(MethodsApp._get_methods(svc))

    assert svc._amqp_consume_queue.calls == [
        ("unbind", "main", "prsTag.app.data_set.initiator-tag"),
        ("bind", "main", "prsTag.app.data_set.initiator-tag"),
    ]
