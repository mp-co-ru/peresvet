import asyncio
import sys
import types

import pytest
from fastapi import HTTPException

from src.common.authorization import (
    AuthorizationDecision,
    AuthorizationInput,
    amqp_publish_headers,
    authorize_amqp_consume,
    authorize_action,
    reset_authorization_provider_cache,
)


def test_default_authorization_provider_allows_without_configuration(monkeypatch):
    monkeypatch.delenv("PRS_AUTH_PROVIDER", raising=False)
    reset_authorization_provider_cache()

    decision = asyncio.run(authorize_action("prsObject.read"))

    assert decision.allow is True


def test_configured_authorization_provider_can_deny(monkeypatch):
    class DenyProvider:
        async def authorize(self, data: AuthorizationInput) -> AuthorizationDecision:
            assert data.action == "prsTag.data_set"
            assert data.resource == {"tagIds": ["tag-1"]}
            return AuthorizationDecision(allow=False, reason="denied by test policy")

    module = types.ModuleType("fake_auth_provider")
    module.DenyProvider = DenyProvider
    monkeypatch.setitem(sys.modules, "fake_auth_provider", module)
    monkeypatch.setenv("PRS_AUTH_PROVIDER", "fake_auth_provider:DenyProvider")
    reset_authorization_provider_cache()

    with pytest.raises(HTTPException) as ex:
        asyncio.run(
            authorize_action(
                "prsTag.data_set",
                resource={"tagIds": ["tag-1"]},
            )
        )

    assert ex.value.status_code == 403
    assert ex.value.detail == "denied by test policy"


def test_amqp_publish_headers_default_is_empty(monkeypatch):
    monkeypatch.delenv("PRS_AUTH_PROVIDER", raising=False)
    reset_authorization_provider_cache()

    headers = asyncio.run(
        amqp_publish_headers(
            routing_key="prsTag.app_api.data_set.*",
            payload={"data": []},
            reply=True,
        )
    )

    assert headers == {}


def test_configured_provider_can_add_amqp_headers_and_deny_consume(monkeypatch):
    class AmqpProvider:
        async def authorize(self, data: AuthorizationInput) -> AuthorizationDecision:
            if data.action == "amqp.consume":
                assert data.resource["routing_key"] == "prsTag.app_api.data_set.*"
                assert data.environment["headers"] == {"x-prs-security": "signed"}
                return AuthorizationDecision(allow=False, reason="bad service token")
            return AuthorizationDecision(allow=True)

        async def amqp_publish_headers(self, data: AuthorizationInput) -> dict:
            assert data.action == "amqp.publish"
            assert data.resource == {
                "routing_key": "prsTag.app_api.data_set.*",
                "reply": False,
            }
            return {"x-prs-security": "signed"}

    module = types.ModuleType("fake_amqp_auth_provider")
    module.AmqpProvider = AmqpProvider
    monkeypatch.setitem(sys.modules, "fake_amqp_auth_provider", module)
    monkeypatch.setenv("PRS_AUTH_PROVIDER", "fake_amqp_auth_provider:AmqpProvider")
    reset_authorization_provider_cache()

    headers = asyncio.run(
        amqp_publish_headers(
            routing_key="prsTag.app_api.data_set.*",
            payload={"data": []},
            reply=False,
        )
    )
    decision = asyncio.run(
        authorize_amqp_consume(
            routing_key="prsTag.app_api.data_set.*",
            payload={"data": []},
            headers=headers,
            reply_to=None,
            correlation_id=None,
        )
    )

    assert headers == {"x-prs-security": "signed"}
    assert decision.allow is False
    assert decision.reason == "bad service token"
