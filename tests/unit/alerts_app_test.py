import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.common.amqp_rpc import NO_AMQP_RPC_REPLY
from src.services.alerts.app.alerts_app_svc import AlertsApp, select_alarm_episodes


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
    idle = asyncio.run(svc._get_alarms({"parentId": "obj", "fired": False, "getChildren": False}))
    assert idle["data"][0]["id"] == "a1"
    assert idle["data"][0]["fired"] is None
    assert idle["data"][0]["finish"] is None
    assert idle["data"][0]["acked"] is None
    store["a1.alerts_app"]["fired"] = 100
    store["a1.alerts_app"]["tagId"] = "tag-1"
    alarms = asyncio.run(svc._get_alarms({"fired": True}))
    assert alarms["data"][0]["id"] == "a1"
    assert alarms["data"][0]["tagId"] == "tag-1"
    assert alarms["data"][0]["fired"] == 100
    assert alarms["data"][0]["finish"] is None
    assert alarms["data"][0]["acked"] is None
    store["a1.alerts_app"]["fired"] = False
    store["a1.alerts_app"]["episodeStart"] = 100
    store["a1.alerts_app"]["finish"] = 200
    pending = asyncio.run(svc._get_alarms({"parentId": "obj", "fired": False, "getChildren": False}))
    assert pending["data"][0]["fired"] == 100
    assert pending["data"][0]["finish"] == 200
    hidden = asyncio.run(svc._get_alarms({"parentId": "obj", "fired": True, "getChildren": True}))
    assert hidden["data"] == []


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
    bodies = [c.args[0] for c in svc._post_message.await_args_list]
    keys = [c.kwargs["routing_key"] for c in svc._post_message.await_args_list]
    assert any("alarm_on" in k for k in keys)
    assert any("alarm_acked" in k for k in keys)
    assert all("data" not in body for body in bodies)
    assert all(set(body) == {"alertId", "x"} for body in bodies)

    store["a1.alerts_app"]["autoAck"] = False
    store["a1.alerts_app"]["acked"] = False
    asyncio.run(svc._tag_value_changed({"data": [{"tagId": "tag-1", "data": [[200, 5, 0]]}]}, id_alert="a1"))
    assert store["a1.alerts_app"]["fired"] is False
    assert store["a1.alerts_app"]["episodeStart"] == 100
    assert store["a1.alerts_app"]["finish"] == 200

    store["a1.alerts_app"] = {
        "fired": 50, "acked": False, "finish": None, "episodeStart": None,
        "value": 10, "high": True, "autoAck": False, "cn": "hi", "description": "d",
    }
    asyncio.run(svc._ack_alarm({"id": "a1", "x": 60}))
    assert store["a1.alerts_app"]["acked"] == 60
    published = svc._post_message.await_args_list[-1].args[0]
    assert published == {"alertId": "a1", "x": 60}
    asyncio.run(svc._ack_alarm({"id": "a1", "x": 70}))
    assert store["a1.alerts_app"]["acked"] == 60

    asyncio.run(svc._ack_alarm({"id": "missing", "x": 1, "data": {"x": 1}}))
    asyncio.run(svc._created({"id": "a1"}))
    asyncio.run(svc._updated({"id": "a1"}))
    asyncio.run(svc._deleting({"id": "a1"}))
    svc._add_app_handlers()
    assert "prsAlert.app_api.get_alarms" in svc._handlers


def test_ack_keeps_closed_episode_and_cache_restores_it():
    store = {
        "a1.alerts_app": {
            "fired": False,
            "acked": False,
            "episodeStart": 10,
            "finish": 20,
            "value": 10,
            "high": True,
            "autoAck": False,
            "cn": "hi",
            "description": "",
            "tagId": "tag-1",
        }
    }
    svc = _svc(store=store)
    asyncio.run(svc._ack_alarm({"id": "a1"}))
    assert store["a1.alerts_app"]["fired"] is False
    assert store["a1.alerts_app"]["episodeStart"] == 10
    assert store["a1.alerts_app"]["finish"] == 20
    assert isinstance(store["a1.alerts_app"]["acked"], int)
    assert svc._post_message.await_args.args[0]["alertId"] == "a1"
    assert isinstance(svc._post_message.await_args.args[0]["x"], int)

    row = [(
        "a1", None,
        {
            "prsActive": ["TRUE"],
            "cn": ["hi"],
            "description": [""],
            "prsJsonConfigString": ['{"value": 90, "high": true, "autoAck": false}'],
        },
    )]
    restored = {}
    svc2 = _svc(store=restored, alerts=row)
    svc2._hierarchy.search = AsyncMock(return_value=row)

    async def post(mes, reply=False, routing_key=None, timeout=None):
        if routing_key and "alarm_state" in routing_key:
            return {"alertId": "a1", "x": 95, "cx": None, "e": 80}
        return None

    svc2._post_message = post
    assert asyncio.run(svc2._make_alert_cache("a1")) is True
    assert restored["a1.alerts_app"]["fired"] is False
    assert restored["a1.alerts_app"]["episodeStart"] == 95
    assert restored["a1.alerts_app"]["finish"] == 80
    assert restored["a1.alerts_app"]["tagId"] == "tag-1"

    fresh = {}
    svc3 = _svc(store=fresh, alerts=row)
    svc3._hierarchy.search = AsyncMock(return_value=row)

    async def post_open(mes, reply=False, routing_key=None, timeout=None):
        if routing_key and "alarm_state" in routing_key:
            return {"alertId": "a1", "x": 50, "cx": None, "e": None}
        if routing_key and "data_get" in routing_key:
            return {"data": [{"tagId": "tag-1", "data": [[90, 95, 0]]}]}
        return None

    svc3._post_message = post_open
    assert asyncio.run(svc3._make_alert_cache("a1")) is True
    assert fresh["a1.alerts_app"]["fired"] == 50

    closed = {}
    svc4 = _svc(store=closed, alerts=row)
    svc4._hierarchy.search = AsyncMock(return_value=row)

    async def post_closed(mes, reply=False, routing_key=None, timeout=None):
        if routing_key and "alarm_state" in routing_key:
            return {"alertId": "a1", "x": 300, "cx": 320, "e": 310}
        return None

    svc4._post_message = post_closed
    assert asyncio.run(svc4._make_alert_cache("a1")) is True
    assert closed["a1.alerts_app"]["fired"] is False
    assert closed["a1.alerts_app"]["episodeStart"] == 300
    assert closed["a1.alerts_app"]["finish"] == 310
    assert closed["a1.alerts_app"]["acked"] == 320


EPISODES = [
    {"fired": 300, "finish": 310, "acked": 320},
    {"fired": 100, "finish": 180, "acked": 200},
]


def test_select_alarm_episodes_follows_fired_start_and_count():
    active = select_alarm_episodes(EPISODES, fired=True, start=None, finish=150, count=50)
    assert active == [{"fired": 100, "finish": None, "acked": None}]
    assert select_alarm_episodes(EPISODES, fired=True, start=150, finish=305, count=None) == [
        {"fired": 300, "finish": None, "acked": None}
    ]
    state = select_alarm_episodes(EPISODES, fired=False, start=None, finish=150, count=None)
    assert state == [{"fired": 100, "finish": None, "acked": None}]
    listed = select_alarm_episodes(EPISODES, fired=False, start=50, finish=400, count=1)
    assert listed == [{"fired": 300, "finish": 310, "acked": 320}]
    idle = select_alarm_episodes([], fired=False, start=None, finish=150, count=None)
    assert idle == [{"fired": None, "finish": None, "acked": None}]
    closed = select_alarm_episodes(EPISODES, fired=False, start=None, finish=400, count=None)
    assert closed == [{"fired": 300, "finish": 310, "acked": 320}]
    pending = select_alarm_episodes(
        [{"fired": 100, "finish": 180, "acked": None}],
        fired=False, start=None, finish=400, count=None,
    )
    assert pending == [{"fired": 100, "finish": 180, "acked": None}]
    assert select_alarm_episodes([], fired=True, start=None, finish=150, count=None) == []


def test_off_while_acked_keeps_the_episode():
    store = {
        "a1.alerts_app": {
            "fired": 100,
            "acked": 110,
            "finish": None,
            "episodeStart": None,
            "value": 10,
            "high": True,
            "autoAck": True,
            "cn": "hi",
            "description": "d",
        }
    }
    svc = _svc(store=store)
    asyncio.run(svc._tag_value_changed(
        {"data": [{"tagId": "tag-1", "data": [[200, 5, 0]]}]},
        id_alert="a1",
    ))
    alarm = store["a1.alerts_app"]
    assert alarm["fired"] is False
    assert alarm["episodeStart"] == 100
    assert alarm["finish"] == 200
    assert alarm["acked"] == 110


def test_get_alarms_state_returns_closed_episode_from_cache():
    store = {
        "a1.alerts_app": {
            "fired": False,
            "acked": 320,
            "finish": 310,
            "episodeStart": 300,
            "cn": "Высокий уровень",
            "description": "",
            "tagId": "tag-1",
        }
    }
    svc = _svc(store=store, alerts=[("a1", None, {"cn": ["Высокий уровень"]})])
    svc._hierarchy.search = AsyncMock(return_value=[("a1", None, {"cn": ["Высокий уровень"]})])
    res = asyncio.run(svc._get_alarms({
        "parentId": "a1",
        "fired": False,
    }))
    assert res["data"] == [{
        "id": "a1",
        "cn": "Высокий уровень",
        "description": "",
        "tagId": "tag-1",
        "fired": 300,
        "finish": 310,
        "acked": 320,
    }]
    svc._post_message.assert_not_called()


def test_get_alarms_reads_history_when_count_is_set():
    store = {
        "a1.alerts_app": {
            "fired": False,
            "acked": 320,
            "finish": 310,
            "episodeStart": 300,
            "cn": "hi",
            "description": "",
            "tagId": "tag-1",
        }
    }
    svc = _svc(store=store, alerts=[("a1", None, {"cn": ["hi"]})])
    svc._hierarchy.search = AsyncMock(return_value=[("a1", None, {"cn": ["hi"]})])
    svc._post_message = AsyncMock(return_value={"data": EPISODES})
    res = asyncio.run(svc._get_alarms({
        "parentId": "obj",
        "fired": False,
        "count": 2,
    }))
    assert [row["fired"] for row in res["data"]] == [300, 100]
    body = svc._post_message.await_args.args[0]
    assert body["alertId"] == "a1"
    assert body["count"] == 2
    assert "alarm_history.a1" in svc._post_message.await_args.kwargs["routing_key"]


def test_object_without_children_skips_alarms_of_nested_objects():
    parent = "obj"
    parent_dn = "cn=Цех,cn=objects,cn=prs"
    child_dn = "cn=Насос,cn=Цех,cn=objects,cn=prs"
    own = ("a-own", "cn=hi,cn=Уровень," + parent_dn, {"cn": ["own"]})
    nested = ("a-nested", "cn=hi,cn=Уровень," + child_dn, {"cn": ["nested"]})

    async def search(payload):
        if payload.get("id") == parent:
            return [(parent, parent_dn, {"objectClass": ["prsObject"]})]
        classes = (payload.get("filter") or {}).get("objectClass")
        if classes == ["prsAlert"]:
            return [own, nested]
        if classes == ["prsObject"]:
            return [
                (parent, parent_dn, {"objectClass": ["prsObject"]}),
                ("child", child_dn, {"objectClass": ["prsObject"]}),
            ]
        return []

    def alarm(name):
        return {
            "fired": 10,
            "acked": False,
            "finish": None,
            "episodeStart": None,
            "cn": name,
            "description": "",
            "tagId": "t",
        }

    svc = _svc(store={
        "a-own.alerts_app": alarm("own"),
        "a-nested.alerts_app": alarm("nested"),
    })
    svc._hierarchy.search = search
    own_only = asyncio.run(svc._get_alarms({
        "parentId": parent, "fired": True, "getChildren": False,
    }))
    assert [row["id"] for row in own_only["data"]] == ["a-own"]
    both = asyncio.run(svc._get_alarms({
        "parentId": parent, "fired": True, "getChildren": True,
    }))
    assert {row["id"] for row in both["data"]} == {"a-own", "a-nested"}


def test_get_alarms_without_parent_uses_object_and_tag_roots():
    calls = []

    async def search(payload):
        calls.append(payload.get("base"))
        return []

    svc = _svc()
    svc._hierarchy.search = search
    asyncio.run(svc._get_alarms({"fired": True}))
    assert "cn=objects,cn=prs" in calls
    assert "cn=tags,cn=prs" in calls
