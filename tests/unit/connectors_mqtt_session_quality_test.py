import asyncio
import types
from types import MethodType

from src.common.tag_quality_codes import (
    CN_QUALITY_CONNECTION_LOST,
    CN_QUALITY_CONNECTION_RESTORED,
)
from src.services.connectors.app.connectors_mqtt_app_svc import (
    ConnectorsMQTTApp,
    connector_id_from_broker_connection_headers,
)


class _Logger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass

    def debug(self, *args, **kwargs):
        pass

    def log(self, *args, **kwargs):
        pass


CONN_UUID = "86c90602-277b-1041-8738-a50fb7246d3e"


class _BrokerEvent:
    def __init__(self, routing_key, headers):
        self.routing_key = routing_key
        self.headers = headers

    def process(self, ignore_processed=True):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _make_service(*, post_results=None):
    posts = []
    results = list(post_results or [])

    async def _post_message(mes, routing_key=None, reply=False):
        posts.append({"mes": mes, "routing_key": routing_key, "reply": reply})
        if results:
            return results.pop(0)
        if reply:
            return {}
        return True

    svc = types.SimpleNamespace(
        _connected_connectors=set(),
        _connector_session_epoch={},
        _connector_tag_ids={},
        _mqtt_broker_conn_by_connector={},
        _quality_write_ack_timeout_sec=60.0,
        _config=types.SimpleNamespace(svc_name="connectors_mqtt_app"),
        _logger=_Logger(),
        _post_message=_post_message,
        _posts=posts,
        _get_connector_data=None,
        _get_connector_tag_ids=None,
        _get_tag_data=None,
        _hierarchy=None,
    )
    svc._replace_connector_tag_cache = MethodType(
        ConnectorsMQTTApp._replace_connector_tag_cache, svc
    )
    svc._invalidate_connector_session = MethodType(
        ConnectorsMQTTApp._invalidate_connector_session, svc
    )
    svc._connector_session_is_current = MethodType(
        ConnectorsMQTTApp._connector_session_is_current, svc
    )
    svc._load_connector_tag_ids_for_quality = MethodType(
        ConnectorsMQTTApp._load_connector_tag_ids_for_quality, svc
    )
    svc._on_broker_connection_event = MethodType(
        ConnectorsMQTTApp._on_broker_connection_event, svc
    )
    svc._write_connector_tags_quality = MethodType(
        ConnectorsMQTTApp._write_connector_tags_quality, svc
    )
    svc._persist_connection_restored = MethodType(
        ConnectorsMQTTApp._persist_connection_restored, svc
    )
    svc._send_config_to_connector = MethodType(
        ConnectorsMQTTApp._send_config_to_connector, svc
    )
    svc._connection_lost = MethodType(ConnectorsMQTTApp._connection_lost, svc)
    return svc


async def _get_connector_data_ok(conn_id: str) -> dict:
    return {
        "prsActive": True,
        "prsEntityTypeCode": "1",
        "prsJsonConfigString": {},
    }


def test_first_getconfig_writes_101_with_ack_before_full_configuration():
    svc = _make_service()
    svc._connector_tag_ids["conn-1"] = {"tag-a", "tag-b"}

    async def _search(**kwargs):
        return [
            (None, None, {"cn": ["tag-a"], "prsJsonConfigString": ["{}"]}),
            (None, None, {"cn": ["tag-b"], "prsJsonConfigString": ["{}"]}),
        ]

    async def _get_tag_data(conn_id, tag_id):
        return {"id": tag_id}

    svc._get_connector_data = _get_connector_data_ok
    svc._get_tag_data = _get_tag_data
    svc._hierarchy = types.SimpleNamespace(search=_search)

    asyncio.run(
        ConnectorsMQTTApp._send_config_to_connector(
            svc, {"data": {"id": "conn-1"}, "action": "prsConnector.getConfig"}
        )
    )

    assert [p["routing_key"] for p in svc._posts] == [
        "prsTag.app_api.data_set.*",
        "prs2conn.conn-1",
    ]
    quality_post, config_post = svc._posts
    assert quality_post["reply"] is True
    points = {item["tagId"]: item["data"][0] for item in quality_post["mes"]["data"]}
    assert set(points) == {"tag-a", "tag-b"}
    for _tag_id, point in points.items():
        assert point[1] is None
        assert point[2] == CN_QUALITY_CONNECTION_RESTORED
    assert config_post["mes"]["action"] == "prsConnector.full_configuration"
    assert "conn-1" in svc._connected_connectors


def test_repeat_getconfig_does_not_write_101():
    svc = _make_service()
    svc._connected_connectors.add("conn-1")
    svc._connector_tag_ids["conn-1"] = {"tag-a"}

    async def _search(**kwargs):
        return [(None, None, {"cn": ["tag-a"], "prsJsonConfigString": ["{}"]})]

    async def _get_tag_data(conn_id, tag_id):
        return {"id": tag_id}

    svc._get_connector_data = _get_connector_data_ok
    svc._get_tag_data = _get_tag_data
    svc._hierarchy = types.SimpleNamespace(search=_search)

    asyncio.run(
        ConnectorsMQTTApp._send_config_to_connector(
            svc, {"data": {"id": "conn-1"}, "action": "prsConnector.getConfig"}
        )
    )

    assert [p["routing_key"] for p in svc._posts] == ["prs2conn.conn-1"]


def test_failed_101_does_not_send_configuration_and_allows_retry():
    svc = _make_service(post_results=[None])
    svc._connector_tag_ids["conn-1"] = {"tag-a"}

    hierarchy_calls = []

    async def _search(**kwargs):
        hierarchy_calls.append(kwargs)
        return [(None, None, {"cn": ["tag-a"], "prsJsonConfigString": ["{}"]})]

    async def _get_tag_data(conn_id, tag_id):
        return {"id": tag_id}

    svc._get_connector_data = _get_connector_data_ok
    svc._get_tag_data = _get_tag_data
    svc._hierarchy = types.SimpleNamespace(search=_search)

    asyncio.run(
        ConnectorsMQTTApp._send_config_to_connector(
            svc, {"data": {"id": "conn-1"}, "action": "prsConnector.getConfig"}
        )
    )

    assert svc._posts[0]["routing_key"] == "prsTag.app_api.data_set.*"
    assert all(p["routing_key"] != "prs2conn.conn-1" for p in svc._posts)
    assert "conn-1" not in svc._connected_connectors
    assert hierarchy_calls == []


def test_empty_tag_cache_loads_ids_before_101():
    svc = _make_service()
    loaded = []

    async def _get_ids(conn_id):
        loaded.append(conn_id)
        return ["tag-from-ldap"]

    async def _search(**kwargs):
        return [(None, None, {"cn": ["tag-from-ldap"], "prsJsonConfigString": ["{}"]})]

    async def _get_tag_data(conn_id, tag_id):
        return {"id": tag_id}

    svc._get_connector_data = _get_connector_data_ok
    svc._get_connector_tag_ids = _get_ids
    svc._get_tag_data = _get_tag_data
    svc._hierarchy = types.SimpleNamespace(search=_search)

    asyncio.run(
        ConnectorsMQTTApp._send_config_to_connector(
            svc, {"data": {"id": "conn-1"}, "action": "prsConnector.getConfig"}
        )
    )

    assert loaded == ["conn-1"]
    quality_post = svc._posts[0]
    assert quality_post["routing_key"] == "prsTag.app_api.data_set.*"
    assert quality_post["mes"]["data"][0]["tagId"] == "tag-from-ldap"
    assert quality_post["mes"]["data"][0]["data"][0][2] == CN_QUALITY_CONNECTION_RESTORED
    assert quality_post["reply"] is True
    assert svc._posts[1]["routing_key"] == "prs2conn.conn-1"


def test_connection_lost_writes_100_without_ack_and_clears_session():
    svc = _make_service()
    svc._connected_connectors.add("conn-1")
    svc._connector_tag_ids["conn-1"] = {"tag-a"}

    asyncio.run(
        ConnectorsMQTTApp._connection_lost(svc, {"id": "conn-1"})
    )

    assert "conn-1" not in svc._connected_connectors
    assert len(svc._posts) == 1
    assert svc._posts[0]["reply"] is False
    assert svc._posts[0]["mes"]["data"][0]["data"][0][2] == CN_QUALITY_CONNECTION_LOST
    assert svc._connector_session_epoch.get("conn-1") == 1


def test_tagsapp_error_on_101_does_not_send_configuration():
    svc = _make_service(post_results=[{"error": {"code": 500, "message": "fail"}}])
    svc._connector_tag_ids["conn-1"] = {"tag-a"}

    async def _search(**kwargs):
        raise AssertionError("LDAP тегов не должен вызываться")

    svc._get_connector_data = _get_connector_data_ok
    svc._hierarchy = types.SimpleNamespace(search=_search)

    asyncio.run(
        ConnectorsMQTTApp._send_config_to_connector(
            svc, {"data": {"id": "conn-1"}, "action": "prsConnector.getConfig"}
        )
    )

    assert all(p["routing_key"] != "prs2conn.conn-1" for p in svc._posts)
    assert "conn-1" not in svc._connected_connectors


def test_extra_tags_get_second_101_before_configuration():
    svc = _make_service()
    svc._connector_tag_ids["conn-1"] = {"tag-a"}

    async def _search(**kwargs):
        return [
            (None, None, {"cn": ["tag-a"], "prsJsonConfigString": ["{}"]}),
            (None, None, {"cn": ["tag-b"], "prsJsonConfigString": ["{}"]}),
        ]

    async def _get_tag_data(conn_id, tag_id):
        return {"id": tag_id}

    svc._get_connector_data = _get_connector_data_ok
    svc._get_tag_data = _get_tag_data
    svc._hierarchy = types.SimpleNamespace(search=_search)

    asyncio.run(
        ConnectorsMQTTApp._send_config_to_connector(
            svc, {"data": {"id": "conn-1"}, "action": "prsConnector.getConfig"}
        )
    )

    assert [p["routing_key"] for p in svc._posts] == [
        "prsTag.app_api.data_set.*",
        "prsTag.app_api.data_set.*",
        "prs2conn.conn-1",
    ]
    first_ids = {item["tagId"] for item in svc._posts[0]["mes"]["data"]}
    extra_ids = {item["tagId"] for item in svc._posts[1]["mes"]["data"]}
    assert first_ids == {"tag-a"}
    assert extra_ids == {"tag-b"}
    assert svc._posts[0]["reply"] is True
    assert svc._posts[1]["reply"] is True
    assert "conn-1" in svc._connected_connectors


def test_failed_extra_101_does_not_send_configuration():
    svc = _make_service(post_results=[{}, None])
    svc._connector_tag_ids["conn-1"] = {"tag-a"}

    async def _search(**kwargs):
        return [
            (None, None, {"cn": ["tag-a"], "prsJsonConfigString": ["{}"]}),
            (None, None, {"cn": ["tag-b"], "prsJsonConfigString": ["{}"]}),
        ]

    async def _get_tag_data(conn_id, tag_id):
        return {"id": tag_id}

    svc._get_connector_data = _get_connector_data_ok
    svc._get_tag_data = _get_tag_data
    svc._hierarchy = types.SimpleNamespace(search=_search)

    asyncio.run(
        ConnectorsMQTTApp._send_config_to_connector(
            svc, {"data": {"id": "conn-1"}, "action": "prsConnector.getConfig"}
        )
    )

    assert all(p["routing_key"] != "prs2conn.conn-1" for p in svc._posts)
    assert "conn-1" not in svc._connected_connectors


def test_lwt_during_101_persist_skips_configuration_and_keeps_offline():
    svc = _make_service()
    svc._connector_tag_ids["conn-1"] = {"tag-a"}

    async def _post_message(mes, routing_key=None, reply=False):
        svc._posts.append({"mes": mes, "routing_key": routing_key, "reply": reply})
        if reply:
            ConnectorsMQTTApp._invalidate_connector_session(svc, "conn-1")
            return {}
        return True

    async def _search(**kwargs):
        raise AssertionError("не должны собирать конфиг после LWT")

    svc._post_message = _post_message
    svc._get_connector_data = _get_connector_data_ok
    svc._hierarchy = types.SimpleNamespace(search=_search)

    asyncio.run(
        ConnectorsMQTTApp._send_config_to_connector(
            svc, {"data": {"id": "conn-1"}, "action": "prsConnector.getConfig"}
        )
    )

    assert all(p["routing_key"] != "prs2conn.conn-1" for p in svc._posts)
    assert "conn-1" not in svc._connected_connectors


def test_wait_ack_timeout_does_not_send_configuration():
    svc = _make_service()
    svc._connector_tag_ids["conn-1"] = {"tag-a"}
    svc._quality_write_ack_timeout_sec = 0.01

    async def _post_message(mes, routing_key=None, reply=False):
        svc._posts.append({"mes": mes, "routing_key": routing_key, "reply": reply})
        if reply:
            await asyncio.sleep(0.2)
            return {}
        return True

    async def _search(**kwargs):
        raise AssertionError("не должны собирать конфиг после таймаута 101")

    svc._post_message = _post_message
    svc._get_connector_data = _get_connector_data_ok
    svc._hierarchy = types.SimpleNamespace(search=_search)

    asyncio.run(
        ConnectorsMQTTApp._send_config_to_connector(
            svc, {"data": {"id": "conn-1"}, "action": "prsConnector.getConfig"}
        )
    )

    assert all(p["routing_key"] != "prs2conn.conn-1" for p in svc._posts)
    assert "conn-1" not in svc._connected_connectors


def test_broker_headers_extract_mqtt_client_uuid():
    conn_id = connector_id_from_broker_connection_headers(
        {
            "protocol": "MQTT 3.1.1",
            "client_properties": {"client_id": CONN_UUID},
            "pid": "<0.1.0>",
            "name": "1.2.3.4:1234 -> 1.2.3.4:1883",
        }
    )
    assert conn_id == CONN_UUID


def test_broker_headers_ignore_non_mqtt_protocol():
    assert connector_id_from_broker_connection_headers(
        {
            "protocol": [0, 9, 1],
            "port": 1883,
            "client_properties": {"client_id": CONN_UUID},
        }
    ) is None


def test_broker_headers_ignore_amqp_service_connection():
    assert connector_id_from_broker_connection_headers(
        {
            "protocol": [0, 9, 1],
            "port": 5672,
            "user": "prs",
            "client_properties": {"connection_name": "connectors_mqtt_app"},
        }
    ) is None


def test_connection_lost_loads_tag_ids_when_cache_empty():
    svc = _make_service()

    async def _get_ids(conn_id):
        return ["tag-from-ldap"]

    svc._get_connector_tag_ids = _get_ids

    asyncio.run(ConnectorsMQTTApp._connection_lost(svc, {"id": "conn-1"}))

    assert svc._posts[0]["mes"]["data"][0]["tagId"] == "tag-from-ldap"
    assert svc._posts[0]["mes"]["data"][0]["data"][0][2] == CN_QUALITY_CONNECTION_LOST


def test_broker_connection_closed_writes_100():
    svc = _make_service()
    svc._connector_tag_ids[CONN_UUID] = {"tag-a"}
    svc._connected_connectors.add(CONN_UUID)
    svc._mqtt_broker_conn_by_connector[CONN_UUID] = "<0.1.0>|mqtt-a"

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


def test_stale_broker_connection_closed_is_ignored():
    svc = _make_service()
    svc._connector_tag_ids[CONN_UUID] = {"tag-a"}
    svc._connected_connectors.add(CONN_UUID)
    svc._mqtt_broker_conn_by_connector[CONN_UUID] = "<0.2.0>|mqtt-new"

    asyncio.run(
        ConnectorsMQTTApp._on_broker_connection_event(
            svc,
            _BrokerEvent(
                "connection.closed",
                {
                    "protocol": "MQTT",
                    "pid": "<0.1.0>",
                    "name": "mqtt-old",
                    "client_properties": {"client_id": CONN_UUID},
                },
            ),
        )
    )

    assert CONN_UUID in svc._connected_connectors
    assert svc._posts == []
