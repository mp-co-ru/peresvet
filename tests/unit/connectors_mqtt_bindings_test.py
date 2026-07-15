import asyncio
import types

from src.services.connectors.app.connectors_mqtt_app_svc import ConnectorsMQTTApp


class _Logger:
    def info(self, *args, **kwargs):
        pass


class _Queue:
    def __init__(self):
        self.calls = []

    async def bind(self, exchange, routing_key):
        self.calls.append(("bind", exchange, routing_key))

    async def unbind(self, exchange, routing_key):
        self.calls.append(("unbind", exchange, routing_key))


def _make_service():
    return types.SimpleNamespace(
        _amqp_consume_queue=_Queue(),
        _exchange="main",
        _config=types.SimpleNamespace(svc_name="connectors_mqtt_app"),
        _logger=_Logger(),
    )


def test_bind_conn_uses_unbind_when_requested():
    svc = _make_service()

    asyncio.run(ConnectorsMQTTApp._bind_conn(svc, "conn-1", False))

    assert svc._amqp_consume_queue.calls == [
        ("unbind", "main", "prsConnector.model.link_tag.conn-1"),
        ("unbind", "main", "prsConnector.model.tag_link_updated.conn-1"),
        ("unbind", "main", "prsConnector.model.unlink_tag.conn-1"),
        ("unbind", "main", "prsConnector.model.tag_updated.conn-1"),
        ("unbind", "main", "prsConnector.model.tag_deleted.conn-1"),
        ("unbind", "main", "prsConnector.model.updated.conn-1"),
        ("unbind", "main", "prsConnector.model.deleted.conn-1"),
        ("unbind", "main", "prsConnector.connection_lost.conn-1"),
    ]


def test_bind_conn_uses_bind_when_requested():
    svc = _make_service()

    asyncio.run(ConnectorsMQTTApp._bind_conn(svc, "conn-1", True))

    assert svc._amqp_consume_queue.calls == [
        ("bind", "main", "prsConnector.model.link_tag.conn-1"),
        ("bind", "main", "prsConnector.model.tag_link_updated.conn-1"),
        ("bind", "main", "prsConnector.model.unlink_tag.conn-1"),
        ("bind", "main", "prsConnector.model.tag_updated.conn-1"),
        ("bind", "main", "prsConnector.model.tag_deleted.conn-1"),
        ("bind", "main", "prsConnector.model.updated.conn-1"),
        ("bind", "main", "prsConnector.model.deleted.conn-1"),
        ("bind", "main", "prsConnector.connection_lost.conn-1"),
    ]
