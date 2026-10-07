import asyncio
import types

from src.services.methods.model_crud.methods_model_crud_svc import MethodsModelCRUD


class _Logger:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def debug(self, *args, **kwargs):
        pass

    def warning(self, msg, *args, **kwargs):
        self.warnings.append(msg)

    def error(self, msg, *args, **kwargs):
        self.errors.append(msg)


class _Queue:
    def __init__(self):
        self.calls = []

    async def bind(self, exchange, routing_key):
        self.calls.append(("bind", exchange, routing_key))

    async def unbind(self, exchange, routing_key):
        self.calls.append(("unbind", exchange, routing_key))


class _RedisJson:
    def __init__(self, store, wrap_root=False):
        self.store = store
        self.wrap_root = wrap_root

    def _maybe_wrap(self, val):
        if self.wrap_root and val is not None:
            return [val]
        return val

    async def get(self, key, *args, **kwargs):
        return self._maybe_wrap(self.store.get(key))

    async def set(self, name, path, obj):
        if path == "$":
            self.store[name] = obj
        else:
            current = self.store.setdefault(name, [])
            if isinstance(current, list):
                if path not in current:
                    current.append(obj)
            elif isinstance(current, dict):
                current[path] = obj

    async def delete(self, key, path=None):
        if path is None:
            self.store.pop(key, None)
            return
        value = self.store.get(key)
        if isinstance(value, dict):
            value.pop(path, None)

    async def arrpop(self, key, path, index):
        value = self.store.get(key)
        if isinstance(value, list) and 0 <= index < len(value):
            return value.pop(index)
        return None


class _Redis:
    def __init__(self, store, wrap_root=False):
        self.store = store
        self.wrap_root = wrap_root

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def json(self):
        return _RedisJson(self.store, wrap_root=self.wrap_root)


class _Cache:
    def __init__(self, wrap_root=False):
        self.store = {}
        self.wrap_root = wrap_root

    def get_redis(self):
        return _Redis(self.store, wrap_root=self.wrap_root)


class _Hierarchy:
    def __init__(self, *, missing_nodes=None, present_methods=None):
        self.missing_nodes = set(missing_nodes or [])
        self.present_methods = set(present_methods or [])
        self.deleted = []

    async def search(self, payload):
        base = payload.get("base")
        if base in self.missing_nodes:
            raise ValueError(f"Узел {base} не найден.")
        cn_filter = (payload.get("filter") or {}).get("cn")
        if isinstance(cn_filter, list):
            cn = cn_filter[0] if cn_filter else None
        else:
            cn = cn_filter
        if base in self.present_methods and cn_filter is not None and cn not in (None, "*", "initiatedBy"):
            return [(f"{base}:{cn}", f"cn={cn},cn=initiatedBy,{base}", {"cn": [cn]})]
        if base in self.present_methods and cn == "initiatedBy":
            return [(f"{base}:initiatedBy", f"cn=initiatedBy,{base}", {"cn": ["initiatedBy"]})]
        return []

    async def delete(self, node_id):
        self.deleted.append(node_id)


def _make_service(hierarchy, wrap_root=False):
    svc = object.__new__(MethodsModelCRUD)
    svc._hierarchy = hierarchy
    svc._cache = _Cache(wrap_root=wrap_root)
    svc._amqp_consume_queue = _Queue()
    svc._exchange = "main"
    svc._config = types.SimpleNamespace(
        svc_name="methods_model_crud",
        hierarchy={"class": "prsMethod"},
    )
    svc._logger = _Logger()
    svc._posted = []

    async def _post_message(mes, routing_key=None, reply=False):
        svc._posted.append((mes, routing_key))

    svc._post_message = _post_message
    return svc


def test_delete_initiator_wrapped_cache_does_not_clear_other_schedule():
    hierarchy = _Hierarchy(
        missing_nodes=["dead-method"],
        present_methods=["live-method"],
    )
    svc = _make_service(hierarchy, wrap_root=True)
    svc._cache.store["deleted-tag.methods_model_crud"] = ["dead-method", "live-method"]
    svc._cache.store["other-sched.methods_model_crud"] = ["sibling-method"]

    asyncio.run(
        MethodsModelCRUD._delete_initiator(
            svc,
            {"id": "deleted-tag"},
            "prsTag.model.deleted.deleted-tag",
        )
    )

    assert "deleted-tag.methods_model_crud" not in svc._cache.store
    assert svc._cache.store["other-sched.methods_model_crud"] == ["sibling-method"]
    assert hierarchy.deleted == ["live-method:deleted-tag"]


def test_delete_initiator_continues_after_missing_method_and_keeps_other_cache():
    hierarchy = _Hierarchy(
        missing_nodes=["dead-method"],
        present_methods=["live-method"],
    )
    svc = _make_service(hierarchy)
    svc._cache.store["deleted-tag.methods_model_crud"] = ["dead-method", "live-method"]
    svc._cache.store["other-sched.methods_model_crud"] = ["sibling-method"]

    asyncio.run(
        MethodsModelCRUD._delete_initiator(
            svc,
            {"id": "deleted-tag"},
            "prsTag.model.deleted.deleted-tag",
        )
    )

    assert "deleted-tag.methods_model_crud" not in svc._cache.store
    assert svc._cache.store["other-sched.methods_model_crud"] == ["sibling-method"]
    assert hierarchy.deleted == ["live-method:deleted-tag"]
    assert svc._posted == [
        ({"id": "live-method"}, "prsMethod.model.updated.live-method")
    ]
    assert any("dead-method" in msg for msg in svc._logger.errors)
    assert ("unbind", "main", "prsTag.model.deleted.deleted-tag") in svc._amqp_consume_queue.calls


def test_remove_method_from_wrapped_initiator_cache_keeps_sibling():
    hierarchy = _Hierarchy()
    svc = _make_service(hierarchy, wrap_root=True)
    svc._cache.store["sched-1.methods_model_crud"] = ["method-a", "method-b"]

    async def _run():
        async with svc._cache.get_redis() as r:
            removed = await MethodsModelCRUD._remove_method_from_initiator_cache(
                svc, r, "sched-1", "method-a", "prsSchedule"
            )
            return removed

    removed = asyncio.run(_run())

    assert removed is False
    assert svc._cache.store["sched-1.methods_model_crud"] == ["method-b"]
    assert all(call[0] != "unbind" for call in svc._amqp_consume_queue.calls)


def test_remove_last_method_from_initiator_cache_deletes_key():
    hierarchy = _Hierarchy()
    svc = _make_service(hierarchy)
    svc._cache.store["sched-1.methods_model_crud"] = ["method-a"]

    async def _run():
        async with svc._cache.get_redis() as r:
            return await MethodsModelCRUD._remove_method_from_initiator_cache(
                svc, r, "sched-1", "method-a", "prsSchedule"
            )

    removed = asyncio.run(_run())

    assert removed is True
    assert "sched-1.methods_model_crud" not in svc._cache.store
    assert ("unbind", "main", "prsSchedule.model.deleted.sched-1") in svc._amqp_consume_queue.calls


def test_get_method_initiators_treats_missing_method_as_already_removed():
    hierarchy = _Hierarchy(missing_nodes=["gone-method"])
    svc = _make_service(hierarchy)

    result = asyncio.run(MethodsModelCRUD._get_method_initiators(svc, "gone-method"))

    assert result == []
    assert any("gone-method" in msg for msg in svc._logger.warnings)


def test_delete_method_cache_does_not_fail_whole_handler_on_missing_method():
    hierarchy = _Hierarchy(
        missing_nodes=["dead-method"],
        present_methods=["live-method"],
    )
    svc = _make_service(hierarchy)
    svc._cache.store["sched-1.methods_model_crud"] = ["dead-method", "live-method"]

    async def _get_initiators(method_id):
        if method_id == "dead-method":
            raise ValueError(f"Узел {method_id} не найден.")
        return [("sched-1", {"objectClass": ["prsSchedule"]})]

    svc._get_method_initiators = _get_initiators

    asyncio.run(MethodsModelCRUD._delete_method_cache(svc, ["dead-method", "live-method"]))

    assert svc._cache.store["sched-1.methods_model_crud"] == ["dead-method"]
    assert any("dead-method" in msg for msg in svc._logger.warnings)
