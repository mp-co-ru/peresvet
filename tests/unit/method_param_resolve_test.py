import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.services.methods.app.method_param_resolve import parse_parameter_config, resolve_parameter_value


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
