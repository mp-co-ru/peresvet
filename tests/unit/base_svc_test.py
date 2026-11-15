"""Поведение базовых сервисов без брокера, LDAP и Redis."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aio_pika
import ldap
import pytest
from aiormq.abc import DeliveredMessage
from pamqp.commands import Basic

from src.common.amqp_rpc import NO_AMQP_RPC_REPLY
from src.common.app_svc import AppSvc
from src.common.app_svc_settings import AppSvcSettings
from src.common.authorization import AuthorizationContextMiddleware, get_current_amqp_context
from src.common.base_svc import BaseSvc
from src.common.base_svc_settings import BaseSvcSettings
from src.common.logger import PrsLogger
from src.common.svc import Svc
from src.common.svc_settings import SvcSettings
from src.common import base_svc as base_mod


class _Log:
    def __init__(self):
        self.messages = []

    def debug(self, message):
        self.messages.append(("debug", message))

    def info(self, message):
        self.messages.append(("info", message))

    def warning(self, message):
        self.messages.append(("warning", message))

    def error(self, message):
        self.messages.append(("error", message))


class _Incoming:
    def __init__(self, body, routing_key="cmd", reply_to="reply", correlation_id="cid", headers=None):
        self.body = body if isinstance(body, bytes) else body.encode()
        self.routing_key = routing_key
        self.reply_to = reply_to
        self.correlation_id = correlation_id
        self.headers = headers
        self.acked = 0
        self.rejected = None
        self.process_flags = []

    def process(self, ignore_processed=True):
        self.process_flags.append(ignore_processed)
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def ack(self):
        self.acked += 1

    async def reject(self, requeue=False):
        self.rejected = requeue


def _bare(**config):
    svc = BaseSvc.__new__(BaseSvc)
    svc._conf = SimpleNamespace(
        svc_name="unit_base",
        broker={
            "amqp_url": "amqp://unit",
            "name": "peresvet",
            "durable": True,
            "auto_delete": False,
        },
        cache_url="redis://unit",
        ldap_url="ldap://unit",
        **config,
    )
    svc._logger = _Log()
    svc._initialized = True
    svc._handlers = {}
    svc._callback_futures = {}
    svc._exchange = SimpleNamespace(publish=AsyncMock())
    svc._amqp_callback_queue = SimpleNamespace(name="callback-queue")
    svc._amqp_channel = SimpleNamespace(close=AsyncMock())
    svc._amqp_connection = SimpleNamespace(close=AsyncMock())
    return svc


def _published_message(call):
    if "message" in call.kwargs:
        return call.kwargs["message"]
    return call.args[0]


def _published_json(call):
    return json.loads(_published_message(call).body.decode())


@pytest.fixture
def quiet_logger(monkeypatch):
    monkeypatch.setattr(PrsLogger, "make_logger", lambda **kwargs: _Log())


@pytest.fixture
def loop_policy():
    previous = asyncio.get_event_loop_policy()
    yield
    asyncio.set_event_loop_policy(previous)


@pytest.fixture
def service_names():
    before = set(BaseSvc._registered_service_names)
    yield
    BaseSvc._registered_service_names.intersection_update(before)


def test_init_registers_service_and_own_hooks(quiet_logger, loop_policy, service_names):
    settings = BaseSvcSettings(svc_name="unit-base-init")
    svc = BaseSvc(settings, title="unit")

    assert "unit-base-init" in BaseSvc.registered_service_names()
    assert svc._config is svc._conf
    assert svc._initialized is False
    assert svc._handlers == {}
    assert svc._cache is None
    assert svc.router.on_startup == [svc.on_startup]
    assert svc.router.on_shutdown == [svc.on_shutdown]
    assert any(item.cls is AuthorizationContextMiddleware for item in svc.user_middleware)
    assert asyncio.run(svc._check_mes_correctness({"a": 1})) is True
    assert asyncio.run(svc._reject_message({"a": 1})) is False
    svc._set_handlers()
    assert svc._handlers == {}
    assert any("Начало инициализации" in message for _level, message in svc._logger.messages)


def test_init_keeps_caller_lifecycle_hooks(quiet_logger, loop_policy, service_names):
    started = []
    stopped = []

    def extra_start():
        started.append("extra")

    def extra_stop():
        stopped.append("extra")

    settings = BaseSvcSettings(svc_name="unit-base-hooks")
    svc = BaseSvc(settings, on_startup=[extra_start], on_shutdown=(extra_stop,))

    assert svc.router.on_startup == [extra_start, svc.on_startup]
    assert svc.router.on_shutdown == [extra_stop, svc.on_shutdown]


def test_process_message_waits_and_drops_invalid_payloads(monkeypatch):
    svc = _bare()
    svc._initialized = False

    async def wake(_delay):
        svc._initialized = True

    monkeypatch.setattr(asyncio, "sleep", wake)
    message = _Incoming(b"{}")
    asyncio.run(svc._process_message(message))
    assert message.process_flags == [True]
    assert message.acked == 1

    svc._initialized = True

    async def invalid(_message):
        return False

    svc._check_mes_correctness = invalid
    bad = _Incoming(b'{"a": 1}')
    asyncio.run(svc._process_message(bad))
    assert bad.acked == 1
    assert any("Неправильный формат" in message for level, message in svc._logger.messages if level == "error")

    broken = _Incoming(b"not-json")
    svc._check_mes_correctness = BaseSvc._check_mes_correctness.__get__(svc, BaseSvc)
    asyncio.run(svc._process_message(broken))
    assert broken.acked == 1
    assert any("не в формате json" in message for level, message in svc._logger.messages if level == "error")

    async def reject(_message):
        return True

    svc._reject_message = reject
    rejected = _Incoming(b'{"a": 1}')
    asyncio.run(svc._process_message(rejected))
    assert rejected.rejected is True
    assert rejected.acked == 0
    assert any("отклонено" in message for level, message in svc._logger.messages if level == "debug")


def test_process_message_denied_by_policy_replies_403(monkeypatch):
    svc = _bare()
    handled = []

    async def handler(mes, routing_key):
        handled.append(routing_key)
        return {"ok": True}

    async def deny(**_kwargs):
        return SimpleNamespace(allow=False, reason="")

    svc._handlers = {"cmd": handler}
    monkeypatch.setattr(base_mod, "authorize_amqp_consume", deny)
    silent = _Incoming(b'{"a": 1}', reply_to=None)
    asyncio.run(svc._process_message(silent))
    assert silent.acked == 1
    assert handled == []
    svc._exchange.publish.assert_not_called()
    assert get_current_amqp_context() is None

    async def deny_with_reason(**_kwargs):
        return SimpleNamespace(allow=False, reason="closed")

    monkeypatch.setattr(base_mod, "authorize_amqp_consume", deny_with_reason)
    denied = _Incoming(b'{"a": 1}', headers=None)
    asyncio.run(svc._process_message(denied))
    payload = _published_json(svc._exchange.publish.await_args)
    assert payload == {"error": {"code": 403, "message": "closed"}}
    assert svc._exchange.publish.await_args.kwargs["routing_key"] == "reply"
    assert any("closed" in message for level, message in svc._logger.messages if level == "warning")


def test_process_message_dispatches_first_match_and_replies(monkeypatch):
    svc = _bare()
    calls = []
    seen_context = {}

    async def first(mes, routing_key):
        calls.append(("first", routing_key, mes))
        seen_context["during"] = get_current_amqp_context()
        return {"value": (1, "да")}

    async def second(mes, routing_key):
        calls.append(("second", routing_key))
        return {"no": True}

    async def headers(**_kwargs):
        return {"x-actor": "operator"}

    svc._handlers = {r"tag\..*": first, "tag.1": second}
    monkeypatch.setattr(base_mod, "authorize_amqp_consume", AsyncMock(return_value=SimpleNamespace(allow=True, reason=None)))
    monkeypatch.setattr(base_mod, "amqp_publish_headers", headers)
    message = _Incoming(b'{"n": 1}', routing_key="tag.1", headers={"hop": "1"})
    asyncio.run(svc._process_message(message))

    assert calls == [("first", "tag.1", {"n": 1})]
    assert message.acked == 1
    assert seen_context["during"]["routing_key"] == "tag.1"
    assert seen_context["during"]["headers"] == {"hop": "1"}
    assert get_current_amqp_context() is None
    published = svc._exchange.publish.await_args
    assert published.kwargs["routing_key"] == "reply"
    assert _published_message(published).correlation_id == "cid"
    assert _published_message(published).headers == {"x-actor": "operator"}
    assert _published_json(published) == {"value": [1, "да"]}


def test_process_message_skips_reply_without_subscriber_or_handler(monkeypatch):
    svc = _bare()
    calls = []

    async def side(mes, routing_key):
        calls.append(routing_key)
        return NO_AMQP_RPC_REPLY

    monkeypatch.setattr(base_mod, "authorize_amqp_consume", AsyncMock(return_value=SimpleNamespace(allow=True, reason=None)))
    svc._handlers = {"cmd": side}
    asyncio.run(svc._process_message(_Incoming(b'{"a": 1}')))
    svc._exchange.publish.assert_not_called()

    async def answer(mes, routing_key):
        return {"ok": True}

    svc._handlers = {"cmd": answer}
    asyncio.run(svc._process_message(_Incoming(b'{"a": 1}', reply_to=None)))
    svc._exchange.publish.assert_not_called()

    svc._handlers = {"other": answer}
    missed = _Incoming(b'{"a": 1}', routing_key="cmd")
    asyncio.run(svc._process_message(missed))
    assert any("не обработано" in message for level, message in svc._logger.messages if level == "warning")
    assert calls == ["cmd"]


def test_process_message_reports_handler_and_publish_failures(monkeypatch):
    svc = _bare()

    async def broken(mes, routing_key):
        raise RuntimeError("handler failed")

    monkeypatch.setattr(base_mod, "authorize_amqp_consume", AsyncMock(return_value=SimpleNamespace(allow=True, reason=None)))
    svc._handlers = {"cmd": broken}
    svc._exchange.publish = AsyncMock(side_effect=RuntimeError("broker down"))
    message = _Incoming(b'{"a": 1}')
    asyncio.run(svc._process_message(message))
    assert any("handler failed" in text for _level, text in svc._logger.messages)
    assert any("Не удалось отправить ответ об ошибке RPC" in text for _level, text in svc._logger.messages)
    assert get_current_amqp_context() is None

    async def unserializeable(mes, routing_key):
        return object()

    svc._logger = _Log()
    svc._handlers = {"cmd": unserializeable}
    svc._exchange.publish = AsyncMock()
    asyncio.run(svc._process_message(_Incoming(b'{"a": 1}', correlation_id="")))
    svc._exchange.publish.assert_not_called()
    assert any("Не удалось сериализовать" in text for _level, text in svc._logger.messages)

    svc._exchange.publish = AsyncMock()
    asyncio.run(svc._process_message(_Incoming(b'{"a": 1}', correlation_id="cid-2")))
    payload = _published_json(svc._exchange.publish.await_args)
    assert payload["error"]["code"] == 500
    assert "JSON" in payload["error"]["message"]


def test_post_message_fire_and_forget_rpc_and_unroutable():
    svc = _bare()

    assert asyncio.run(svc._post_message({"a": 1}, routing_key=None)) is None
    svc._exchange.publish.assert_not_called()
    assert any("routing_key" in text for _level, text in svc._logger.messages)

    async def publish_ok(message, routing_key):
        assert routing_key == "tags.created"
        assert json.loads(message.body.decode()) == {"a": 1}
        assert message.reply_to is None
        assert message.headers == {}
        return object()

    svc._exchange.publish = publish_ok
    assert asyncio.run(svc._post_message({"a": 1}, routing_key="tags.created")) is True

    async def publish_missing(message, routing_key):
        return DeliveredMessage(
            delivery=Basic.Return(reply_code=312, reply_text="NO_ROUTE"),
            header=None,
            body=b"",
            channel=None,
        )

    svc._exchange.publish = publish_missing
    assert asyncio.run(svc._post_message({"a": 1}, reply=True, routing_key="missing")) is None
    assert svc._callback_futures == {}

    async def publish_returned(message, routing_key):
        return DeliveredMessage(
            delivery=Basic.Return(reply_code=200),
            header=None,
            body=b"",
            channel=None,
        )

    svc._exchange.publish = publish_returned
    assert asyncio.run(svc._post_message({"a": 1}, routing_key="returned")) is True

    async def publish_and_answer(message, routing_key):
        correlation_id = message.correlation_id
        assert message.reply_to == "callback-queue"
        assert routing_key == "rpc"

        async def finish():
            while correlation_id not in svc._callback_futures:
                await asyncio.sleep(0)
            future = svc._callback_futures.pop(correlation_id)
            future.set_result({"echo": message.body.decode()})

        asyncio.get_running_loop().create_task(finish())
        return None

    svc._exchange.publish = publish_and_answer
    reply = asyncio.run(svc._post_message({"q": "да"}, reply=True, routing_key="rpc"))
    assert reply == {"echo": '{"q": "да"}'}
    assert svc._callback_futures == {}

    async def publish_and_fail(message, routing_key):
        correlation_id = message.correlation_id

        async def finish():
            while correlation_id not in svc._callback_futures:
                await asyncio.sleep(0)
            svc._callback_futures[correlation_id].set_exception(RuntimeError("rpc failed"))

        asyncio.get_running_loop().create_task(finish())
        return None

    svc._logger = _Log()
    svc._exchange.publish = publish_and_fail
    assert asyncio.run(svc._post_message({"q": 1}, reply=True, routing_key="rpc")) is None
    assert svc._callback_futures == {}
    assert any("Ошибка получения результата" in text for _level, text in svc._logger.messages)


def test_on_rpc_response_resolves_denies_and_ignores_duplicates(monkeypatch):
    svc = _bare()
    asyncio.run(svc._on_rpc_response(SimpleNamespace(correlation_id=None)))
    assert any("correlation_id" in text for _level, text in svc._logger.messages)

    loop = asyncio.new_event_loop()
    future = loop.create_future()
    svc._callback_futures["cid"] = future
    message = SimpleNamespace(
        correlation_id="cid",
        body=b'{"ok": true}',
        routing_key="callback-queue",
        headers={"h": "1"},
        reply_to=None,
    )
    asyncio.run(svc._on_rpc_response(message))
    assert future.result() == {"ok": True}
    assert "cid" not in svc._callback_futures
    loop.close()

    svc._logger = _Log()
    asyncio.run(svc._on_rpc_response(message))
    assert any("повторный ответ" in text for level, text in svc._logger.messages if level == "debug")

    loop = asyncio.new_event_loop()
    denied = loop.create_future()
    svc._callback_futures["deny"] = denied

    async def deny(**_kwargs):
        return SimpleNamespace(allow=False, reason=None)

    monkeypatch.setattr(base_mod, "authorize_amqp_consume", deny)
    asyncio.run(
        svc._on_rpc_response(
            SimpleNamespace(
                correlation_id="deny",
                body=b'{"secret": 1}',
                routing_key="callback-queue",
                headers=None,
                reply_to="src",
            )
        )
    )
    assert denied.result()["error"]["code"] == 403
    assert denied.result()["error"]["message"] == "Доступ запрещён политикой безопасности."
    loop.close()

    loop = asyncio.new_event_loop()
    broken = loop.create_future()
    svc._callback_futures["bad"] = broken
    svc._logger = _Log()
    asyncio.run(
        svc._on_rpc_response(
            SimpleNamespace(
                correlation_id="bad",
                body=b"{",
                routing_key="callback-queue",
                headers={},
                reply_to=None,
            )
        )
    )
    assert broken.done() is False
    assert "bad" not in svc._callback_futures
    assert any("Ошибка работы с ответом" in text for _level, text in svc._logger.messages)
    loop.close()


def test_startup_retries_broker_then_cache_and_shutdown(monkeypatch):
    svc = _bare()
    svc._initialized = False
    svc._handlers = {"created": None, "updated.*": None}
    sleeps = []
    attempts = {"n": 0}

    class _Queue:
        def __init__(self, name):
            self.name = name
            self.binds = []
            self.consumers = []

        async def bind(self, exchange, routing_key):
            self.binds.append((exchange, routing_key))

        async def consume(self, callback, no_ack=False):
            self.consumers.append((callback, no_ack))

    class _Channel:
        def __init__(self):
            self.qos = None
            self.exchange_args = None
            self.queues = []

        async def set_qos(self, prefetch):
            self.qos = prefetch

        async def declare_exchange(self, name, exchange_type, durable, auto_delete):
            self.exchange_args = (name, exchange_type, durable, auto_delete)
            return "exchange"

        async def declare_queue(self, name=None, durable=False, auto_delete=False, exclusive=False):
            queue = _Queue(name or "anon")
            self.queues.append((queue, durable, auto_delete, exclusive))
            return queue

        async def close(self):
            self.closed = True

    class _Connection:
        def __init__(self, channel):
            self.channel_obj = channel
            self.closed = False

        async def channel(self):
            return self.channel_obj

        async def close(self):
            self.closed = True

    channel = _Channel()
    connection = _Connection(channel)

    async def connect_robust(url, loop):
        assert url == "amqp://unit"
        assert loop is asyncio.get_running_loop()
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise aio_pika.AMQPException("broker down")
        return connection

    async def sleep(delay):
        sleeps.append(delay)

    class _Cache:
        def __init__(self, url):
            self.url = url

    monkeypatch.setattr(base_mod.aio_pika, "connect_robust", connect_robust)
    monkeypatch.setattr(base_mod, "RedisCache", _Cache)
    monkeypatch.setattr(asyncio, "sleep", sleep)

    asyncio.run(svc.on_startup())

    assert attempts["n"] == 2
    assert sleeps == [5]
    assert svc._initialized is True
    assert svc._cache.url == "redis://unit"
    assert channel.qos == 1
    assert channel.exchange_args == ("peresvet", "topic", True, False)
    consume_queue, callback_queue = [item[0] for item in channel.queues]
    assert consume_queue.name == "unit_base_consume"
    assert [key for _exchange, key in consume_queue.binds] == ["created", "updated.*"]
    assert consume_queue.consumers == [(svc._process_message, False)]
    assert callback_queue.binds == [("exchange", "anon")]
    assert callback_queue.consumers == [(svc._on_rpc_response, True)]
    assert any("Связь с AMQP" in text for level, text in svc._logger.messages if level == "info")
    assert any("Ошибка связи с брокером" in text for level, text in svc._logger.messages if level == "error")

    asyncio.run(svc.on_shutdown())
    assert connection.closed is True


def test_svc_ldap_connect_retries_each_failure(monkeypatch):
    svc = Svc.__new__(Svc)
    svc._config = SimpleNamespace(svc_name="unit_svc", ldap_url="ldap://bad")
    svc._logger = _Log()
    failures = [ValueError("uri"), ldap.SERVER_DOWN("down"), RuntimeError("other")]

    class _Hierarchy:
        def __init__(self):
            self.calls = 0

        async def connect(self):
            self.calls += 1
            if failures:
                raise failures.pop(0)

    svc._hierarchy = _Hierarchy()
    sleeps = []

    async def sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    asyncio.run(svc._ldap_connect())
    assert sleeps == [5, 5, 5]
    assert svc._hierarchy.calls == 4
    errors = [text for level, text in svc._logger.messages if level == "error"]
    assert any("Неверный формат URI" in text and "ldap://bad" in text for text in errors)
    assert sum("Ошибка связи с сервером ldap" in text for text in errors) == 2
    assert any("Связь с LDAP" in text for level, text in svc._logger.messages if level == "info")


def test_svc_and_app_construct_hierarchy_and_startup(quiet_logger, loop_policy, service_names, monkeypatch):
    svc_settings = SvcSettings(svc_name="unit-svc-init", ldap_url="ldap://svc")
    svc = Svc(svc_settings, title="svc")
    assert svc._hierarchy.url == "ldap://svc"

    app_settings = AppSvcSettings(
        svc_name="unit-app-init",
        ldap_url="ldap://app",
        hierarchy={"class": "prsTag"},
        nodes=["node-7"],
    )
    app = AppSvc(app_settings, title="app")
    assert app._hierarchy.url == "ldap://app"
    assert "prsTag.model.updated.node-7" in app._handlers
    assert "prsTag.model.created" not in app._handlers

    order = []

    async def amqp_connect():
        order.append("amqp")

    async def cache_connect():
        order.append("cache")

    async def ldap_connect():
        order.append("ldap")

    svc._logger = _Log()
    svc._amqp_connect = amqp_connect
    svc._cache_connect = cache_connect
    svc._ldap_connect = ldap_connect
    asyncio.run(svc.on_startup())
    assert order == ["amqp", "cache", "ldap"]

    called = {}

    async def parent_startup(self):
        called["parent"] = True

    monkeypatch.setattr(Svc, "on_startup", parent_startup)
    asyncio.run(app.on_startup())
    assert called["parent"] is True


def test_app_svc_queue_names_and_default_lifecycle():
    app = AppSvc.__new__(AppSvc)
    app._config = SimpleNamespace(nodes=[], svc_name="tags_app")
    app._handlers = {"created": None, "deleted.*": None}
    declared = []

    class _Channel:
        async def declare_queue(self, name=None, durable=False, auto_delete=False, exclusive=False):
            declared.append(name)
            return SimpleNamespace(name=name or "generated", binds=[])

    app._amqp_channel = _Channel()
    app._exchange = "exchange"
    asyncio.run(app._generate_queue())
    assert declared == ["tags_app_consume"]

    binds = []

    async def bind(exchange, routing_key):
        binds.append(routing_key)

    app._amqp_consume_queue.bind = bind
    asyncio.run(app._bind_queue())
    assert binds == ["created", "deleted.*"]

    app._config = SimpleNamespace(nodes=["node-1", "node-2"], svc_name="tags_app")
    asyncio.run(app._generate_queue())
    assert declared[-1] == "tags_app_consume_node-1"

    assert asyncio.run(app._created({"id": "1"}, "created")) is None
    for method in (app._may_update, app._updating, app._updated, app._may_delete, app._deleting, app._deleted):
        assert asyncio.run(method({"id": "1"}, "key")) == {"response": True}
    app._add_app_handlers()
