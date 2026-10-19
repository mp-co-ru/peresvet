import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from src.services.methods.app.method_param_resolve import (
    interpret_http_response,
    parse_parameter_config,
    prepare_http_request,
    resolve_parameter_value,
)


def test_parse_parameter_config():
    assert parse_parameter_config({}) == {}
    assert parse_parameter_config("  ") == {}
    assert parse_parameter_config('{"a": 1}') == {"a": 1}
    assert parse_parameter_config({"a": 1}) == {"a": 1}
    with pytest.raises(TypeError):
        parse_parameter_config(1)


def test_resolve_routing_key_and_jsonata():
    post = AsyncMock(return_value={"data": 7})

    async def fake_eval(expr, data, timeout_ms=None):
        return data["data"]

    with patch("src.services.methods.app.method_param_resolve.evaluate_jsonata", fake_eval):
        val = asyncio.run(
            resolve_parameter_value(
                {"routingKey": "rk", "message": {"x": 1}, "responseJsonata": "data", "clientStub": {}},
                post_message=post,
                client_request=None,
                initiator_finish=1,
                initiator_point=None,
            )
        )
    assert val == 7
    post.assert_awaited()


def test_resolve_legacy_tag_and_client_context():
    post = AsyncMock(return_value={"y": 1})
    val = asyncio.run(
        resolve_parameter_value(
            {"tagId": "t1"},
            post_message=post,
            client_request=None,
            initiator_finish=9,
            initiator_point=None,
            virtual_resolution_tag_id="t1",
        )
    )
    assert val == {"y": 1}
    mes = post.await_args.kwargs["mes"]
    assert mes["evalContextTagId"] == "t1"
    ctx = asyncio.run(
        resolve_parameter_value(
            {},
            post_message=post,
            client_request={"finish": 1},
            initiator_finish=1,
            initiator_point=None,
        )
    )
    assert ctx["finish"] == 1
    built = asyncio.run(
        resolve_parameter_value(
            {},
            post_message=post,
            client_request=None,
            initiator_finish=5,
            initiator_point=(1, 2, 3),
        )
    )
    assert built["point"]["y"] == 2
    with pytest.raises(ValueError):
        asyncio.run(
            resolve_parameter_value(
                {},
                post_message=post,
                client_request=None,
                initiator_finish=None,
                initiator_point=None,
            )
        )
    with pytest.raises(ValueError):
        asyncio.run(
            resolve_parameter_value(
                {"routingKey": "rk", "message": []},
                post_message=post,
                client_request=None,
                initiator_finish=1,
                initiator_point=None,
            )
        )


def test_resolve_catalog_bindings_keep_legacy_paths():
    post = AsyncMock(return_value={"data": [{"data": [[1, 4, None]]}]})
    tag_value = asyncio.run(
        resolve_parameter_value(
            {"binding": "tag", "tagId": "t1"},
            post_message=post,
            client_request=None,
            initiator_finish=3,
            initiator_point=None,
        )
    )
    assert tag_value["data"][0]["data"][0][1] == 4
    assert post.await_args.kwargs["routing_key"] == "prsTag.app_api_client.data_get.*"
    literal = asyncio.run(
        resolve_parameter_value(
            {"binding": "literal", "value": "2.5", "valueTypeCode": 2},
            post_message=post,
            client_request=None,
            initiator_finish=1,
            initiator_point=None,
        )
    )
    assert literal == 2.5

    async def lookup(constant_id):
        assert constant_id == "c1"
        return 9

    constant = asyncio.run(
        resolve_parameter_value(
            {"binding": "constant", "constantId": "c1"},
            post_message=post,
            client_request=None,
            initiator_finish=1,
            initiator_point=None,
            lookup_constant=lookup,
        )
    )
    assert constant == 9
    with pytest.raises(ValueError):
        asyncio.run(
            resolve_parameter_value(
                {"binding": "tag", "tagId": "t1", "routingKey": "rk"},
                post_message=post,
                client_request=None,
                initiator_finish=1,
                initiator_point=None,
            )
        )


def test_prepare_http_request_accepts_http_and_json_body():
    method, url, headers, body = prepare_http_request(
        {
            "method": "post",
            "url": "https://device.local/hook",
            "headers": {"X-Trace": "1"},
            "body": {"a": 1},
        }
    )
    assert method == "POST"
    assert url == "https://device.local/hook"
    assert headers["Content-Type"] == "application/json"
    assert headers["X-Trace"] == "1"
    assert json.loads(body) == {"a": 1}
    with pytest.raises(ValueError):
        prepare_http_request({"url": "file:///etc/passwd"})
    with pytest.raises(ValueError):
        prepare_http_request({"method": "GET"})
    with pytest.raises(ValueError):
        prepare_http_request({"url": "https://ok", "headers": {"Bad\nName": "1"}})


def test_interpret_http_response_json_text_and_errors():
    assert interpret_http_response(200, "application/json", b'{"v": 3}') == {"v": 3}
    assert interpret_http_response(200, "text/plain", b"ok") == "ok"
    with pytest.raises(ValueError, match="HTTP 503"):
        interpret_http_response(503, "text/plain", b"down")
    with pytest.raises(ValueError, match="1 МБ"):
        interpret_http_response(200, "text/plain", b"x" * (1_000_001))


def test_resolve_external_http_request():
    async def fake_perform(method, url, headers, body):
        assert method == "GET"
        assert url == "http://192.168.1.20/value"
        assert headers["Accept"] == "application/json"
        assert body is None
        return 200, "application/json", b'{"value": 4.5}'

    with patch("src.services.methods.app.method_param_resolve._perform_http_request", fake_perform):
        value = asyncio.run(
            resolve_parameter_value(
                {
                    "httpRequest": {
                        "method": "GET",
                        "url": "http://192.168.1.20/value",
                        "headers": {"Accept": "application/json"},
                    },
                    "responseJsonata": "value",
                    "clientStub": {"ignored": True},
                },
                post_message=AsyncMock(),
                client_request=None,
                initiator_finish=1,
                initiator_point=None,
            )
        )
    assert value == 4.5
