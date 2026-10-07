import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.common.amqp_rpc import NO_AMQP_RPC_REPLY
from src.services.alerts.app.alerts_app_svc import AlertsApp


class _Logger:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.debugs = []
        self.infos = []

    def error(self, msg, *a, **k):
        self.errors.append(msg)

    def warning(self, msg, *a, **k):
        self.warnings.append(msg)

    def debug(self, msg, *a, **k):
        self.debugs.append(msg)

    def info(self, msg, *a, **k):
        self.infos.append(msg)


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

    async def get(self, name, *a, **k):
        return self.store.get(name)

    async def set(self, name, path="$", obj=None, **k):
        self.store[name] = obj

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


def _svc(store=None, alerts=None, parent="tag-1"):
    svc = object.__new__(AlertsApp)
    svc._config = SimpleNamespace(svc_name="alerts_app", hierarchy={"class": "prsAlert"})
    svc._logger = _Logger()
    svc._cache = SimpleNamespace(get_redis=lambda: _Redis(store if store is not None else {}))
    svc._amqp_consume_queue = _Queue()
    svc._exchange = "ex"
    svc._post_message = AsyncMock(return_value=None)
    svc._hierarchy = SimpleNamespace(
        get_parent=AsyncMock(return_value=(parent, None)),
        search=AsyncMock(return_value=alerts if alerts is not None else []),
    )
    svc._handlers = {}
    return svc


def test_bind_unbind_last_alert():
    svc = _svc(alerts=[])
    asyncio.run(svc._bind_alert("a1"))
    assert ("bind", "prsTag.app.data_set.tag-1") in svc._amqp_consume_queue.calls
    asyncio.run(svc._unbind_alert("a1"))
    assert ("unbind", "prsTag.app.data_set.tag-1") in svc._amqp_consume_queue.calls

    sibling = _svc(alerts=[("a2", None, {"prsActive": ["TRUE"]})])
    asyncio.run(sibling._unbind_alert("a1"))
    assert not any(c[0] == "unbind" for c in sibling._amqp_consume_queue.calls)


def test_make_alert_cache_and_get_alarms():
    store = {}
    row = [(
        "a1",
        None,
        {
            "prsActive": ["TRUE"],
            "cn": ["hi"],
            "description": ["d"],
            "prsJsonConfigString": ['{"value": 10, "high": true, "autoAck": false}'],
        },
    )]
    svc = _svc(store=store, alerts=row)
    svc._hierarchy.search = AsyncMock(return_value=row)
    active = asyncio.run(svc._make_alert_cache("a1"))
    assert active is True
    assert store["a1.alerts_app"]["value"] == 10
    svc._hierarchy.search = AsyncMock(return_value=row)
    alarms = asyncio.run(svc._get_alarms({"parentId": "obj", "fired": False, "getChildren": False}))
    assert alarms["data"][0]["cn"] == "hi"
    store["a1.alerts_app"]["fired"] = False
    fired_only = asyncio.run(svc._get_alarms({"parentId": "obj", "fired": True, "getChildren": True}))
    assert fired_only["data"] == []


def test_make_alert_cache_invalid_and_inactive():
    svc = _svc()
    svc._hierarchy.search = AsyncMock(return_value=[])
    assert asyncio.run(svc._make_alert_cache("a1")) is None
    svc._hierarchy.search = AsyncMock(return_value=[
        ("a1", None, {"prsActive": ["FALSE"], "cn": ["x"], "description": ["d"], "prsJsonConfigString": ["{}"]})
    ])
    assert asyncio.run(svc._make_alert_cache("a1")) is False
    svc._hierarchy.search = AsyncMock(return_value=[
        ("a1", None, {"prsActive": ["TRUE"], "cn": ["x"], "description": ["d"], "prsJsonConfigString": ["nope"]})
    ])
    assert asyncio.run(svc._make_alert_cache("a1")) is None


def test_tag_value_changed_high_alarm_on_off_and_ack():
    store = {
        "a1.alerts_app": {
            "fired": False,
            "acked": False,
            "value": 10,
            "high": True,
            "autoAck": True,
            "cn": "hi",
            "description": "d",
        }
    }
    svc = _svc(store=store)
    mes = {"data": [{"tagId": "tag-1", "data": [[100, 12, 0]]}]}
    assert asyncio.run(svc._tag_value_changed(mes, id_alert="a1")) is NO_AMQP_RPC_REPLY
    assert store["a1.alerts_app"]["fired"] == 100
    assert store["a1.alerts_app"]["acked"] == 100
    keys = [c.kwargs["routing_key"] for c in svc._post_message.await_args_list]
    assert any("alarm_on" in k for k in keys)
    assert any("alarm_acked" in k for k in keys)

    store["a1.alerts_app"]["autoAck"] = False
    store["a1.alerts_app"]["acked"] = False
    asyncio.run(svc._tag_value_changed({"data": [{"tagId": "tag-1", "data": [[200, 5, 0]]}]}, id_alert="a1"))
    assert store["a1.alerts_app"]["fired"] is None

    store["a1.alerts_app"] = {
        "fired": 50, "acked": False, "value": 10, "high": True, "autoAck": False, "cn": "hi", "description": "d"
    }
    asyncio.run(svc._ack_alarm({"id": "a1", "x": 60, "data": {"x": 60}}))
    assert store["a1.alerts_app"]["acked"] == 60

    asyncio.run(svc._ack_alarm({"id": "missing", "x": 1, "data": {"x": 1}}))
    asyncio.run(svc._created({"id": "a1"}))
    asyncio.run(svc._updated({"id": "a1"}))
    asyncio.run(svc._deleting({"id": "a1"}))
    svc._add_app_handlers()
    assert "prsAlert.app_api.get_alarms" in svc._handlers
