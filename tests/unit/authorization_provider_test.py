import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from src.common.authorization import (
    AllowAllAuthorizationProvider,
    AuthorizationDecision,
    AuthorizationInput,
    amqp_publish_headers,
    authorize_action,
    authorize_amqp_consume,
    get_authorization_provider,
    get_current_amqp_context,
    get_current_request,
    reset_authorization_provider_cache,
    reset_current_amqp_context,
    set_current_amqp_context,
)


class Deny:
    async def authorize(self, data):
        return AuthorizationDecision(allow=False, reason="nope")

    async def amqp_publish_headers(self, data):
        return {"x": "1"}


def test_allow_all_and_amqp_context():
    reset_authorization_provider_cache()
    provider = get_authorization_provider()
    assert isinstance(provider, AllowAllAuthorizationProvider)
    token = set_current_amqp_context({"actor": "u"})
    assert get_current_amqp_context()["actor"] == "u"
    reset_current_amqp_context(token)
    assert get_current_amqp_context() is None
    assert get_current_request() is None
    decision = asyncio.run(authorize_action("objects.read"))
    assert decision.allow is True
    headers = asyncio.run(amqp_publish_headers(service_name="s", routing_key="rk", payload={}, reply=False))
    assert headers == {}
    cons = asyncio.run(authorize_amqp_consume(service_name="s", routing_key="rk", payload={}, headers=None, reply_to=None, correlation_id=None))
    assert cons.allow is True


def test_custom_provider_deny_and_headers(monkeypatch):
    reset_authorization_provider_cache()
    monkeypatch.setenv("PRS_AUTH_PROVIDER", "tests.unit.authorization_provider_test:Deny")
    reset_authorization_provider_cache()
    with pytest.raises(HTTPException) as ei:
        asyncio.run(authorize_action("objects.delete"))
    assert ei.value.status_code == 403
    headers = asyncio.run(amqp_publish_headers(service_name="s", routing_key="rk", payload={}, reply=True))
    assert headers == {"x": "1"}
    reset_authorization_provider_cache()
    monkeypatch.delenv("PRS_AUTH_PROVIDER", raising=False)
    reset_authorization_provider_cache()


def test_provider_spec_validation(monkeypatch):
    from src.common.authorization import _load_provider_from_spec

    with pytest.raises(ValueError):
        _load_provider_from_spec("bad-spec")

    class NoAuth:
        pass

    monkeypatch.setitem(__import__("sys").modules, "tmp_no_auth", SimpleNamespace(NoAuth=NoAuth))
    with pytest.raises(TypeError):
        _load_provider_from_spec("tmp_no_auth:NoAuth")
