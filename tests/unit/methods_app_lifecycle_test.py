import asyncio
import types

from src.services.methods.app.methods_app_svc import MethodsApp


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
            self.store.setdefault(name, {})[path] = obj

    async def delete(self, key, path=None):
        if path is None:
            self.store.pop(key, None)
            return
        value = self.store.get(key)
        if isinstance(value, dict):
            value.pop(path, None)


class _Pipeline:
    def __init__(self, store, wrap_root=False):
        self.store = store
        self.wrap_root = wrap_root
        self._commands = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def json(self):
        return self

    def delete(self, key, path=None):
        self._commands.append(("delete", key, path))
        return self

    def get(self, key, *args, **kwargs):
        self._commands.append(("get", key))
        return self

    async def execute(self):
        json_api = _RedisJson(self.store, wrap_root=self.wrap_root)
        results = []
        for cmd in self._commands:
            if cmd[0] == "delete":
                _, key, path = cmd
                await json_api.delete(key, path)
                results.append(1)
            elif cmd[0] == "get":
                results.append(await json_api.get(cmd[1]))
        self._commands.clear()
        return results


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

    def pipeline(self):
        return _Pipeline(self.store, wrap_root=self.wrap_root)


class _Cache:
    def __init__(self, wrap_root=False):
        self.store = {}
        self.wrap_root = wrap_root

    def get_redis(self):
        return _Redis(self.store, wrap_root=self.wrap_root)


class _Hierarchy:
    def __init__(
        self,
        *,
        method_ids=None,
        method_type=0,
        initiators=None,
        initiator_classes=None,
        parent_tag_id="result-tag",
        method_active=True,
    ):
        self.method_ids = method_ids or ["method-1"]
        self.method_type = method_type
        self.initiators = initiators or []
        self.initiator_classes = initiator_classes or {}
        self.parent_tag_id = parent_tag_id
        self.failing_methods = set()
        self.missing_nodes = set()
        self.method_active = method_active

    def _initiators_for(self, method_id):
        if isinstance(self.initiators, dict):
            return self.initiators.get(method_id, [])
        return self.initiators

    def _method_id_from_initiated_by_base(self, base):
        parts = [part[3:] for part in str(base).split(",") if part.startswith("cn=")]
        return parts[2] if len(parts) > 2 else ""

    async def search(self, payload):
        base = payload.get("base")
        if base in self.missing_nodes:
            raise ValueError(f"Узел {base} не найден.")
        node_id = payload.get("id")
        if node_id in self.missing_nodes:
            return []
        if payload.get("filter") == {"objectClass": ["prsMethod"], "prsActive": ["TRUE"]}:
            return [(method_id, None, {"cn": [method_id]}) for method_id in self.method_ids]
        if payload.get("id") and payload.get("attributes") == ["prsActive"]:
            method_id = payload["id"]
            if isinstance(self.method_active, dict):
                active = self.method_active.get(method_id, True)
            else:
                active = self.method_active
            return [(method_id, None, {"prsActive": ["TRUE" if active else "FALSE"]})]
        if payload.get("id") and payload.get("attributes") == ["prsEntityTypeCode"]:
            method_id = payload["id"]
            if isinstance(self.method_type, dict):
                code = self.method_type.get(method_id, 0)
            else:
                code = self.method_type
            return [(method_id, None, {"prsEntityTypeCode": [str(code)]})]
        if str(payload.get("base", "")).startswith("cn=initiatedBy,cn=system,"):
            method_id = self._method_id_from_initiated_by_base(payload.get("base", ""))
            return [
                (initiator_id, None, {"cn": [initiator_id]})
                for initiator_id in self._initiators_for(method_id)
            ]
        return []

    async def get_node_dn(self, method_id):
        if method_id in self.missing_nodes:
            raise ValueError(f"Узел {method_id} не найден.")
        if method_id in self.failing_methods:
            raise RuntimeError(f"ldap failed for {method_id}")
        return f"cn={method_id},cn=methods,cn=prs"

    async def get_node_class(self, node_id):
        return self.initiator_classes.get(node_id, "prsTag")

    async def get_parent(self, method_id):
        if isinstance(self.parent_tag_id, dict):
            return self.parent_tag_id.get(method_id, "result-tag"), None
        return self.parent_tag_id, None


def _make_service(hierarchy, wrap_root=False):
    svc = object.__new__(MethodsApp)
    svc._hierarchy = hierarchy
    svc._cache = _Cache(wrap_root=wrap_root)
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


def test_delete_method_cache_tolerates_missing_initiator_key():
    svc = _make_service(_Hierarchy())
    svc._cache.store["method-1.methods_app"] = ["missing-initiator-id", "existing-initiator-id"]
    svc._cache.store["existing-initiator-id.methods_app"] = {
        "method-1": "result-tag",
        "other-method": "other-tag",
    }

    asyncio.run(MethodsApp._delete_method_cache(svc, "method-1"))

    assert "method-1.methods_app" not in svc._cache.store
    assert "missing-initiator-id.methods_app" not in svc._cache.store
    assert svc._cache.store["existing-initiator-id.methods_app"] == {"other-method": "other-tag"}


def test_get_methods_rebuilds_after_stale_missing_initiator_cache():
    hierarchy = _Hierarchy(
        method_ids=["method-1", "method-2"],
        initiators={
            "method-1": ["good-initiator-1"],
            "method-2": ["good-initiator-2"],
        },
    )
    svc = _make_service(hierarchy)
    svc._cache.store["method-1.methods_app"] = [
        "missing-initiator-id",
        "existing-initiator-id",
    ]
    svc._cache.store["existing-initiator-id.methods_app"] = {"method-1": "stale-tag"}

    asyncio.run(MethodsApp._get_methods(svc))

    assert svc._logger.errors == []
    assert ("bind", "main", "prsTag.app.data_set.good-initiator-1") in svc._amqp_consume_queue.calls
    assert ("bind", "main", "prsTag.app.data_set.good-initiator-2") in svc._amqp_consume_queue.calls
    assert svc._cache.store["method-1.methods_app"] == ["good-initiator-1"]
    assert svc._cache.store["method-2.methods_app"] == ["good-initiator-2"]
    assert svc._cache.store["good-initiator-1.methods_app"] == {"method-1": "result-tag"}
    assert svc._cache.store["good-initiator-2.methods_app"] == {"method-2": "result-tag"}
    assert "missing-initiator-id.methods_app" not in svc._cache.store
    assert "existing-initiator-id.methods_app" not in svc._cache.store


def test_get_methods_continues_after_one_method_fails():
    hierarchy = _Hierarchy(
        method_ids=["broken-method", "method-2"],
        initiators={"method-2": ["good-initiator-2"]},
    )
    hierarchy.failing_methods.add("broken-method")
    svc = _make_service(hierarchy)

    asyncio.run(MethodsApp._get_methods(svc))

    assert any("broken-method" in msg for msg in svc._logger.errors)
    assert ("bind", "main", "prsTag.app.data_set.good-initiator-2") in svc._amqp_consume_queue.calls
    assert svc._cache.store["method-2.methods_app"] == ["good-initiator-2"]


def test_deleting_shared_schedule_method_does_not_unbind_fire_event():
    hierarchy = _Hierarchy(
        method_ids=["method-a", "method-b"],
        initiators={
            "method-a": ["sched-1"],
            "method-b": ["sched-1"],
        },
        initiator_classes={"sched-1": "prsSchedule"},
    )
    svc = _make_service(hierarchy)
    asyncio.run(MethodsApp._make_method_cache(svc, "method-a"))
    asyncio.run(MethodsApp._make_method_cache(svc, "method-b"))
    svc._amqp_consume_queue.calls.clear()

    asyncio.run(MethodsApp._deleting(svc, {"id": "method-a"}))

    assert ("unbind", "main", "prsSchedule.app.fire_event.sched-1") not in svc._amqp_consume_queue.calls
    assert svc._cache.store["sched-1.methods_app"] == {"method-b": "result-tag"}
    assert "method-a.methods_app" not in svc._cache.store


def test_deactivating_shared_schedule_method_does_not_unbind_fire_event():
    hierarchy = _Hierarchy(
        method_ids=["method-a", "method-b"],
        initiators={
            "method-a": ["sched-1"],
            "method-b": ["sched-1"],
        },
        initiator_classes={"sched-1": "prsSchedule"},
        method_active={"method-a": False, "method-b": True},
    )
    svc = _make_service(hierarchy)
    asyncio.run(MethodsApp._make_method_cache(svc, "method-a"))
    asyncio.run(MethodsApp._make_method_cache(svc, "method-b"))
    svc._amqp_consume_queue.calls.clear()

    asyncio.run(MethodsApp._updated(svc, {"id": "method-a"}))

    assert ("unbind", "main", "prsSchedule.app.fire_event.sched-1") not in svc._amqp_consume_queue.calls
    assert svc._cache.store["sched-1.methods_app"] == {"method-b": "result-tag"}


def test_deleting_shared_tag_method_does_not_unbind_data_set():
    hierarchy = _Hierarchy(
        method_ids=["method-a", "method-b"],
        initiators={
            "method-a": ["tag-1"],
            "method-b": ["tag-1"],
        },
        initiator_classes={"tag-1": "prsTag"},
    )
    svc = _make_service(hierarchy)
    asyncio.run(MethodsApp._make_method_cache(svc, "method-a"))
    asyncio.run(MethodsApp._make_method_cache(svc, "method-b"))
    svc._amqp_consume_queue.calls.clear()

    asyncio.run(MethodsApp._deleting(svc, {"id": "method-a"}))

    assert ("unbind", "main", "prsTag.app.data_set.tag-1") not in svc._amqp_consume_queue.calls
    assert svc._cache.store["tag-1.methods_app"] == {"method-b": "result-tag"}
    assert "method-a.methods_app" not in svc._cache.store


def test_deleting_last_schedule_method_unbinds_fire_event_and_deletes_key():
    hierarchy = _Hierarchy(
        initiators=["sched-1"],
        initiator_classes={"sched-1": "prsSchedule"},
    )
    svc = _make_service(hierarchy)
    asyncio.run(MethodsApp._make_method_cache(svc, "method-1"))
    svc._amqp_consume_queue.calls.clear()

    asyncio.run(MethodsApp._deleting(svc, {"id": "method-1"}))

    assert ("unbind", "main", "prsSchedule.app.fire_event.sched-1") in svc._amqp_consume_queue.calls
    assert "sched-1.methods_app" not in svc._cache.store
    assert "method-1.methods_app" not in svc._cache.store


def test_start_method_by_sched_skips_missing_node_and_runs_remaining():
    hierarchy = _Hierarchy(
        method_ids=["dead-method", "live-method"],
        initiators={"live-method": ["sched-1"]},
        initiator_classes={"sched-1": "prsSchedule"},
    )
    hierarchy.missing_nodes.add("dead-method")
    svc = _make_service(hierarchy)
    svc._cache.store["sched-1.methods_app"] = {
        "dead-method": "tag-dead",
        "live-method": "result-tag",
    }
    invoked = []

    async def _calc_tag(tag_id, method_id, parameters, data):
        invoked.append(method_id)

    svc._calc_tag = _calc_tag

    asyncio.run(MethodsApp._start_method_by_sched(svc, {"id": "sched-1", "time": 123}))

    assert invoked == ["live-method"]
    assert any("dead-method" in msg for msg in svc._logger.errors)
    assert "dead-method" not in svc._cache.store["sched-1.methods_app"]
    assert svc._cache.store["sched-1.methods_app"] == {"live-method": "result-tag"}


def test_updated_missing_method_does_not_indexerror_and_cleans_only_this_method():
    hierarchy = _Hierarchy(
        initiators={
            "method-a": ["sched-1"],
            "method-b": ["sched-1"],
        },
        initiator_classes={"sched-1": "prsSchedule"},
    )
    hierarchy.missing_nodes.add("method-a")
    svc = _make_service(hierarchy)
    svc._cache.store["method-a.methods_app"] = ["sched-1"]
    svc._cache.store["method-b.methods_app"] = ["sched-1"]
    svc._cache.store["sched-1.methods_app"] = {
        "method-a": "result-tag",
        "method-b": "result-tag",
    }

    asyncio.run(MethodsApp._updated(svc, {"id": "method-a"}))

    assert svc._cache.store["sched-1.methods_app"] == {"method-b": "result-tag"}
    assert "method-a.methods_app" not in svc._cache.store
    assert ("unbind", "main", "prsSchedule.app.fire_event.sched-1") not in svc._amqp_consume_queue.calls


def test_delete_method_cache_unwraps_json_root_and_keeps_sibling():
    hierarchy = _Hierarchy()
    svc = _make_service(hierarchy, wrap_root=True)
    svc._cache.store["method-1.methods_app"] = ["sched-1"]
    svc._cache.store["sched-1.methods_app"] = {
        "method-1": "result-tag",
        "method-b": "other-tag",
    }

    asyncio.run(MethodsApp._delete_method_cache(svc, "method-1"))

    assert "method-1.methods_app" not in svc._cache.store
    assert svc._cache.store["sched-1.methods_app"] == {"method-b": "other-tag"}


def _shared_schedule_objects(*, wrap_root=False, extra_initiators=None):
    initiators = {
        "method-a": ["sched-speeds"],
        "method-b": ["sched-speeds"],
    }
    initiator_classes = {"sched-speeds": "prsSchedule"}
    if extra_initiators:
        for method_id, ids in extra_initiators.items():
            initiators[method_id] = list(initiators.get(method_id, [])) + list(ids)
            for initiator_id in ids:
                initiator_classes.setdefault(initiator_id, "prsTag")
    hierarchy = _Hierarchy(
        method_ids=["method-a", "method-b"],
        method_type=0,
        initiators=initiators,
        initiator_classes=initiator_classes,
        parent_tag_id={"method-a": "tag-speed-a", "method-b": "tag-speed-b"},
    )
    svc = _make_service(hierarchy, wrap_root=wrap_root)
    asyncio.run(MethodsApp._make_method_cache(svc, "method-a"))
    asyncio.run(MethodsApp._make_method_cache(svc, "method-b"))
    invoked = []

    async def _calc_tag(tag_id, method_id, parameters, data):
        invoked.append((method_id, tag_id))

    svc._calc_tag = _calc_tag
    return hierarchy, svc, invoked


def test_object_cascade_does_not_stop_sibling_schedule_methods():
    # Два независимых объекта, один schedule, prsEntityTypeCode=0.
    # Каскад удаления A: prsMethod.model.deleting, пока узел ещё в LDAP.
    # Следующий fire_event должен вызвать только метод B.
    hierarchy, svc, invoked = _shared_schedule_objects()

    asyncio.run(MethodsApp._start_method_by_sched(svc, {"id": "sched-speeds", "time": 1}))
    assert {method_id for method_id, _ in invoked} == {"method-a", "method-b"}

    invoked.clear()
    svc._amqp_consume_queue.calls.clear()
    asyncio.run(MethodsApp._deleting(svc, {"id": "method-a"}))
    hierarchy.missing_nodes.add("method-a")

    assert ("unbind", "main", "prsSchedule.app.fire_event.sched-speeds") not in svc._amqp_consume_queue.calls
    assert svc._cache.store["sched-speeds.methods_app"] == {"method-b": "tag-speed-b"}
    assert "method-a.methods_app" not in svc._cache.store

    asyncio.run(MethodsApp._start_method_by_sched(svc, {"id": "sched-speeds", "time": 2}))

    assert invoked == [("method-b", "tag-speed-b")]


def test_object_cascade_does_not_stop_sibling_schedule_methods_with_redisjson_wrap():
    hierarchy, svc, invoked = _shared_schedule_objects(wrap_root=True)

    asyncio.run(MethodsApp._start_method_by_sched(svc, {"id": "sched-speeds", "time": 1}))
    assert {method_id for method_id, _ in invoked} == {"method-a", "method-b"}

    invoked.clear()
    svc._amqp_consume_queue.calls.clear()
    asyncio.run(MethodsApp._deleting(svc, {"id": "method-a"}))
    hierarchy.missing_nodes.add("method-a")

    assert ("unbind", "main", "prsSchedule.app.fire_event.sched-speeds") not in svc._amqp_consume_queue.calls
    assert svc._cache.store["sched-speeds.methods_app"] == {"method-b": "tag-speed-b"}

    asyncio.run(MethodsApp._start_method_by_sched(svc, {"id": "sched-speeds", "time": 2}))

    assert invoked == [("method-b", "tag-speed-b")]


def test_deleting_already_gone_method_does_not_unbind_sibling_schedule():
    # Каскад LDAP уже снял метод A; one_app ещё обрабатывает deleting/deleted.
    hierarchy, svc, invoked = _shared_schedule_objects()
    hierarchy.missing_nodes.add("method-a")
    svc._amqp_consume_queue.calls.clear()

    asyncio.run(MethodsApp._deleting(svc, {"id": "method-a"}))

    assert ("unbind", "main", "prsSchedule.app.fire_event.sched-speeds") not in svc._amqp_consume_queue.calls
    assert svc._cache.store["sched-speeds.methods_app"] == {"method-b": "tag-speed-b"}

    asyncio.run(MethodsApp._start_method_by_sched(svc, {"id": "sched-speeds", "time": 3}))

    assert invoked == [("method-b", "tag-speed-b")]


def test_tag_initiated_method_on_sibling_still_runs_after_shared_schedule_peer_deleted():
    hierarchy, svc, invoked = _shared_schedule_objects(
        extra_initiators={"method-b": ["tag-counter"]}
    )
    svc._amqp_consume_queue.calls.clear()

    asyncio.run(MethodsApp._deleting(svc, {"id": "method-a"}))
    hierarchy.missing_nodes.add("method-a")

    assert ("unbind", "main", "prsTag.app.data_set.tag-counter") not in svc._amqp_consume_queue.calls
    assert ("unbind", "main", "prsSchedule.app.fire_event.sched-speeds") not in svc._amqp_consume_queue.calls

    asyncio.run(
        MethodsApp._start_method_by_tag(
            svc,
            {
                "data": [
                    {
                        "tagId": "tag-counter",
                        "data": [[4, 473, None]],
                    }
                ]
            },
        )
    )

    assert invoked == [("method-b", "tag-speed-b")]
