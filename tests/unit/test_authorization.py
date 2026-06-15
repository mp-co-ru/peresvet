import asyncio
import sys
import types

import pytest
from fastapi import HTTPException

from src.common.authorization import (
    AuthorizationDecision,
    AuthorizationInput,
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
