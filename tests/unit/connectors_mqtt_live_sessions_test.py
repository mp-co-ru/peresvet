import asyncio
import base64
import types
from types import MethodType

from src.common.tag_quality_codes import CN_QUALITY_CONNECTION_LOST
from src.services.connectors.app.connectors_mqtt_app_svc import (
    ConnectorsMQTTApp,
    connector_id_from_management_connection,
    live_mqtt_connector_ids_from_management_connections,
)
from tests.unit.connectors_mqtt_session_quality_test import (
    CONN_UUID,
    _BrokerEvent,
    _make_service,
)


SIEMENS_UUID = "218cd700-277b-1041-872b-a50fb7246d3e"
FATEK_UUID = "5583eaf2-1615-1041-9758-9da7fb54dde3"


def _mqtt_connection(conn_id: str, *, protocol: str = "MQTT 5-0") -> dict:
    return {
        "protocol": protocol,
        "name": f"10.0.0.8:45039 -> 10.66.0.6:1883",
        "user": "prs",
        "client_properties": {"client_id": conn_id},
    }


def _amqp_connection() -> dict:
    return {
        "protocol": "AMQP 0-9-1",
        "user": "prs",
        "client_properties": {
            "product": "aiormq",
            "client_id": CONN_UUID,
        },
    }


def test_management_connection_extracts_mqtt5_client_uuid():
    assert connector_id_from_management_connection(_mqtt_connection(SIEMENS_UUID)) == SIEMENS_UUID


def test_management_connection_extracts_mqtt311_client_uuid():
    assert (
        connector_id_from_management_connection(
            _mqtt_connection(SIEMENS_UUID, protocol="MQTT 3.1.1")
        )
        == SIEMENS_UUID
    )


def test_management_connection_ignores_amqp_even_with_uuid_property():
    assert connector_id_from_management_connection(_amqp_connection()) is None


def test_management_connection_ignores_non_uuid_mqtt_client():
    assert connector_id_from_management_connection(_mqtt_connection("factory-gateway")) is None


def test_management_connection_ignores_invalid_payload():
    assert connector_id_from_management_connection(None) is None
    assert connector_id_from_management_connection("mqtt") is None


def test_live_mqtt_ids_skip_duplicates_and_non_mqtt():
    ids = live_mqtt_connector_ids_from_management_connections(
        [
            _amqp_connection(),
            _mqtt_connection(SIEMENS_UUID),
            _mqtt_connection(SIEMENS_UUID.upper()),
            _mqtt_connection(FATEK_UUID),
            {"error": "not a connection"},
        ]
    )
    assert ids == [SIEMENS_UUID, FATEK_UUID]


def test_live_mqtt_ids_empty_on_non_list():
    assert live_mqtt_connector_ids_from_management_connections({"error": "no"}) == []
    assert live_mqtt_connector_ids_from_management_connections(None) == []


def test_management_connections_url_uses_amqp_credentials():
    svc = types.SimpleNamespace(
        _config=types.SimpleNamespace(
            broker={"amqp_url": "amqp://prs:secret@rabbit-host:5672/"}
        )
    )
    url, token = ConnectorsMQTTApp._rabbitmq_management_connections_settings(svc)
    assert url.startswith("http://rabbit-host:")
    assert url.endswith("/api/connections")
    assert base64.b64decode(token).decode() == "prs:secret"


def _service_for_restore(*, nodes=None):
    svc = _make_service()
    svc._config.nodes = nodes or []
    svc._config.broker = {"amqp_url": "amqp://prs:secret@rabbitmq/"}
    svc._restore_connected_connectors_from_live_sessions = MethodType(
        ConnectorsMQTTApp._restore_connected_connectors_from_live_sessions, svc
    )
    return svc


def test_restore_from_live_sessions_marks_connected_without_quality_or_config():
    svc = _service_for_restore()

    async def _fetch():
        return [_mqtt_connection(SIEMENS_UUID), _amqp_connection(), _mqtt_connection(FATEK_UUID)]

    svc._fetch_rabbitmq_management_connections = _fetch

    asyncio.run(ConnectorsMQTTApp._restore_connected_connectors_from_live_sessions(svc))

    assert svc._connected_connectors == {SIEMENS_UUID, FATEK_UUID}
    assert svc._posts == []
    assert svc._mqtt_broker_conn_by_connector == {}
    assert svc._connector_session_epoch == {}


def test_restore_skips_session_already_lost_after_subscribe():
    svc = _service_for_restore()
    svc._connector_session_epoch[SIEMENS_UUID] = 1

    async def _fetch():
        return [_mqtt_connection(SIEMENS_UUID), _mqtt_connection(FATEK_UUID)]

    svc._fetch_rabbitmq_management_connections = _fetch

    asyncio.run(ConnectorsMQTTApp._restore_connected_connectors_from_live_sessions(svc))

    assert SIEMENS_UUID not in svc._connected_connectors
    assert FATEK_UUID in svc._connected_connectors
    assert svc._posts == []


def test_restore_filters_by_configured_nodes():
    svc = _service_for_restore(nodes=[SIEMENS_UUID.upper()])

    async def _fetch():
        return [_mqtt_connection(SIEMENS_UUID), _mqtt_connection(FATEK_UUID)]

    svc._fetch_rabbitmq_management_connections = _fetch

    asyncio.run(ConnectorsMQTTApp._restore_connected_connectors_from_live_sessions(svc))

    assert svc._connected_connectors == {SIEMENS_UUID}


def test_restore_does_not_duplicate_already_connected():
    svc = _service_for_restore()
    svc._connected_connectors.add(SIEMENS_UUID)
    logs = []
    svc._logger = types.SimpleNamespace(
        info=lambda msg, *a, **k: logs.append(msg),
        warning=lambda msg, *a, **k: logs.append(msg),
    )

    async def _fetch():
        return [_mqtt_connection(SIEMENS_UUID)]

    svc._fetch_rabbitmq_management_connections = _fetch

    asyncio.run(ConnectorsMQTTApp._restore_connected_connectors_from_live_sessions(svc))

    assert svc._connected_connectors == {SIEMENS_UUID}
    assert logs == []


def test_restore_fetch_error_keeps_disconnected_and_does_not_raise():
    svc = _service_for_restore()
    warnings = []
    svc._logger = types.SimpleNamespace(
        info=lambda *a, **k: None,
        warning=lambda msg, *a, **k: warnings.append(msg),
    )

    async def _fetch():
        raise TimeoutError("management down")

    svc._fetch_rabbitmq_management_connections = _fetch

    asyncio.run(ConnectorsMQTTApp._restore_connected_connectors_from_live_sessions(svc))

    assert svc._connected_connectors == set()
    assert svc._posts == []
    assert warnings
    assert "живым сессиям" in warnings[0] or "MQTT-связи" in warnings[0]


def test_restore_then_broker_closed_still_marks_disconnected():
    svc = _service_for_restore()
    svc._connector_tag_ids[CONN_UUID] = {"tag-a"}

    async def _fetch():
        return [_mqtt_connection(CONN_UUID)]

    svc._fetch_rabbitmq_management_connections = _fetch
    asyncio.run(ConnectorsMQTTApp._restore_connected_connectors_from_live_sessions(svc))
    assert CONN_UUID in svc._connected_connectors

    asyncio.run(
        ConnectorsMQTTApp._on_broker_connection_event(
            svc,
            _BrokerEvent(
                "connection.closed",
                {
                    "protocol": "MQTT",
                    "pid": "<0.1.0>",
                    "name": "mqtt-a",
                    "client_properties": {"client_id": CONN_UUID},
                },
            ),
        )
    )

    assert CONN_UUID not in svc._connected_connectors
    assert svc._posts[0]["mes"]["data"][0]["data"][0][2] == CN_QUALITY_CONNECTION_LOST


def test_fetch_management_connections_returns_empty_on_non_list():
    svc = _service_for_restore()
    svc._rabbitmq_management_connections_settings = lambda: ("http://rabbitmq:15672/api/connections", "token")

    def _fetch_json(url, token):
        return {"error": "not_authorised"}

    svc._fetch_rabbitmq_json = _fetch_json

    payload = asyncio.run(ConnectorsMQTTApp._fetch_rabbitmq_management_connections(svc))
    assert payload == []
