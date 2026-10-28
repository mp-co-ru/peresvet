import asyncio
import json
from pathlib import Path
from types import MethodType, SimpleNamespace
from uuid import UUID

from src.services.connectors.app.connector_config_example import (
    normalize_config_example,
    public_config_example,
)
from src.services.connectors.app.connectors_mqtt_app_svc import ConnectorsMQTTApp


ROOT = Path(__file__).resolve().parents[2]
SAMPLE_RESPONSE = (
    ROOT / "docs/source/samples/connectors/configExampleResponse.txt"
)
CONN_ID = "b61a2360-cc05-103e-9308-555c1a8a1358"


class _Logger:
    def __init__(self):
        self.warnings = []
        self.infos = []

    def info(self, *args, **kwargs):
        self.infos.append(args[0] if args else "")

    def warning(self, *args, **kwargs):
        self.warnings.append(args[0] if args else "")

    def error(self, *args, **kwargs):
        pass

    def debug(self, *args, **kwargs):
        pass


def _sample_data():
    return json.loads(SAMPLE_RESPONSE.read_text(encoding="utf-8"))["data"]


def _example_message():
    return {"action": "prsConnector.config_example", "data": _sample_data()}


class _RedisJson:
    def __init__(self, store):
        self._store = store

    async def get(self, name, *args):
        if name not in self._store:
            raise KeyError(name)
        return self._store[name]

    async def set(self, name, path, obj):
        assert path == "$"
        self._store[name] = obj

    async def delete(self, name, *args):
        self._store.pop(name, None)


class _Cache:
    def __init__(self):
        self.store = {}
        self.client = SimpleNamespace(json=lambda: _RedisJson(self.store))

    def get_redis(self):
        return self

    async def __aenter__(self):
        return self.client

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _service(*, connected=False, camera=False, post=None, cache=None):
    posts = []

    async def _post_message(mes, routing_key=None, reply=False):
        posts.append({"mes": mes, "routing_key": routing_key})
        if post is not None:
            return await post(mes, routing_key)
        return True

    async def _is_camera(conn_id):
        return camera

    svc = SimpleNamespace(
        _config=SimpleNamespace(svc_name="connectors_mqtt_app"),
        _logger=_Logger(),
        _connected_connectors={CONN_ID} if connected else set(),
        _config_examples={},
        _config_example_waiters={},
        _config_example_timeout_sec=0.05,
        _cache=cache,
        _post_message=_post_message,
        _is_camera=_is_camera,
        _posts=posts,
    )
    for name in (
        "_config_example_state",
        "_config_example_cache_key",
        "_read_config_example",
        "_store_config_example",
        "_forget_config_example",
        "accept_config_example",
        "request_config_example",
    ):
        setattr(svc, name, MethodType(getattr(ConnectorsMQTTApp, name), svc))
    return svc


def test_sample_response_normalizes_to_labeled_fields():
    example = normalize_config_example(_sample_data())
    assert example["id"] == CONN_ID
    by_key = {field["key"]: field for field in example["fields"]}
    assert by_key["source.hostTopic"]["name"] == "Корневой топик"
    assert "Zigbee2MQTT" in by_key["source.hostTopic"]["description"]
    assert by_key["source.hostTopic"]["example"] == "zigbee2mqtt"
    assert by_key["source.createDevices"]["type"] == "boolean"
    assert by_key["log.level"]["enum"] == ["DEBUG", "INFO", "WARNING", "ERROR"]
    assert by_key["log.level"]["default"] == "INFO"
    assert by_key["log.fileName"]["default"].endswith(".log")
    assert by_key["source"]["type"] == "object"
    assert "default" not in by_key["source"]
    assert example["example"]["log"]["level"] == "INFO"
    assert example["example"]["log"]["maxBytes"] == 10485760
    assert example["example"]["source"]["hostTopic"] == "zigbee2mqtt"


def test_invalid_example_is_rejected_whole():
    data = _sample_data()
    data["fields"][1]["key"] = "source.host-topic"
    assert normalize_config_example(data) is None
    data = _sample_data()
    data["fields"].append(dict(data["fields"][1]))
    assert normalize_config_example(data) is None
    data = _sample_data()
    data["fields"][1]["example"] = 1
    assert normalize_config_example(data) is None
    data = _sample_data()
    data["fields"][0]["default"] = {}
    assert normalize_config_example(data) is None
    data = _sample_data()
    data["fields"][6]["default"] = "TRACE"
    assert normalize_config_example(data) is None
    data = _sample_data()
    data["example"] = ["not", "an", "object"]
    assert normalize_config_example(data) is None
    legacy = _sample_data()
    legacy.pop("example")
    for field in legacy["fields"]:
        field.pop("default", None)
    legacy_example = normalize_config_example(legacy)
    assert legacy_example is not None
    assert "example" not in legacy_example
    assert "default" not in legacy_example["fields"][1]
    assert public_config_example(CONN_ID, None, "cache", False)["source"] == "none"
    assert public_config_example(CONN_ID, None, "cache", False)["example"] is None


def test_offline_connector_returns_cached_example_without_request():
    svc = _service()
    normalized = normalize_config_example(_sample_data())
    stored = {
        "id": CONN_ID,
        "fields": normalized["fields"],
        "example": normalized["example"],
        "receivedAt": 10,
    }
    svc._config_examples[CONN_ID] = stored

    result = asyncio.run(svc.request_config_example(CONN_ID.upper()))

    assert result["source"] == "cache"
    assert result["connectorAvailable"] is False
    assert result["fields"][1]["name"] == "Корневой топик"
    assert result["example"]["log"]["fileName"].endswith(".log")
    assert result["fields"][6]["default"] == "INFO"
    assert svc._posts == []


def test_online_connector_request_updates_cache_and_redis():
    cache = _Cache()
    svc = _service(connected=True, cache=cache)

    async def post(mes, routing_key):
        assert routing_key == f"prs2conn.{CONN_ID}"
        assert mes["action"] == "prsConnector.config_example"
        assert mes["data"] == {"id": CONN_ID}
        await svc.accept_config_example(_example_message())
        return True

    svc._post_message = post
    result = asyncio.run(svc.request_config_example(CONN_ID))

    assert result["source"] == "connector"
    assert result["connectorAvailable"] is True
    assert result["receivedAt"]
    cached = cache.store[f"{CONN_ID}.connectors_mqtt_app.config_example"]
    assert cached["fields"]
    assert cached["example"]["log"]["maxBytes"] == 10485760
    assert cached["fields"][6]["default"] == "INFO"
    assert result["example"]["log"]["backupCount"] == 10
    again = asyncio.run(svc._read_config_example(CONN_ID))
    assert again["receivedAt"] == result["receivedAt"]
    assert again["example"]["source"]["hostTopic"] == "zigbee2mqtt"


def test_online_timeout_falls_back_to_cache():
    svc = _service(connected=True)
    svc._config_examples[CONN_ID] = {
        "id": CONN_ID,
        "fields": _sample_data()["fields"],
        "receivedAt": 5,
    }

    async def post(mes, routing_key):
        return True

    svc._post_message = post
    result = asyncio.run(svc.request_config_example(CONN_ID))

    assert result["source"] == "cache"
    assert result["connectorAvailable"] is True
    assert any("кэша" in line for line in svc._logger.infos)


def test_parallel_opens_send_one_request():
    svc = _service(connected=True)
    posts = []

    async def post(mes, routing_key):
        posts.append(routing_key)
        await asyncio.sleep(0.02)
        await svc.accept_config_example(_example_message())
        return True

    svc._post_message = post

    async def both():
        return await asyncio.gather(
            svc.request_config_example(CONN_ID),
            svc.request_config_example(CONN_ID),
        )

    first, second = asyncio.run(both())
    assert first["source"] == "connector"
    assert second["source"] == "connector"
    assert posts == [f"prs2conn.{CONN_ID}"]


def test_camera_and_invalid_answer_do_not_replace_cache():
    svc = _service(connected=True, camera=True)
    svc._config_examples[CONN_ID] = {
        "id": CONN_ID,
        "fields": [{"key": "source", "name": "Источник", "type": "object"}],
        "receivedAt": 1,
    }
    result = asyncio.run(svc.request_config_example(CONN_ID))
    assert result["source"] == "none"
    assert result["fields"] == []

    svc = _service(connected=True)

    async def get_data(conn_id):
        raise AssertionError("пример конфигурации не должен собирать full_configuration")

    svc._get_connector_data = get_data
    svc._send_config_to_connector = MethodType(
        ConnectorsMQTTApp._send_config_to_connector, svc
    )
    asyncio.run(
        svc._send_config_to_connector(
            {"action": "prsConnector.config_example", "data": {"id": CONN_ID, "fields": []}}
        )
    )
    assert svc._config_examples == {}
    assert svc._logger.warnings

    asyncio.run(svc.accept_config_example(_example_message()))
    asyncio.run(svc._forget_config_example(CONN_ID))
    assert CONN_ID not in svc._config_examples


def test_delete_removes_cached_example_from_redis():
    cache = _Cache()
    svc = _service(cache=cache)
    stored = asyncio.run(svc._store_config_example(CONN_ID, normalize_config_example(_sample_data())))
    assert stored["id"] == str(UUID(CONN_ID))
    assert cache.store

    async def deleted():
        svc._invalidate_connector_session = lambda conn_id: None
        svc._connector_tag_ids = {}
        svc._connector_session_epoch = {}
        svc._mqtt_broker_conn_by_connector = {}
        svc._connector_log_lines = {}
        svc._connector_command_output_lines = {}

        async def post(mes, routing_key=None, reply=False):
            return True

        svc._post_message = post
        await ConnectorsMQTTApp._deleted(svc, {"id": CONN_ID})

    asyncio.run(deleted())
    assert cache.store == {}
    assert CONN_ID not in svc._config_examples
