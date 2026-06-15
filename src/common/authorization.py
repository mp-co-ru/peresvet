"""Extension points for edition-specific API authorization.

The community edition intentionally keeps the current behaviour: every request is
allowed unless a paid/enterprise package explicitly plugs in another provider via
``PRS_AUTH_PROVIDER``.

The hook is deliberately small and generic. Enterprise code can resolve the
current FastAPI request from the ``request`` field, parse a Bearer token, enrich
the resource from LDAP, and call an external PDP such as OPA. The free edition
does not ship any policy engine and does not require security configuration.
"""

from __future__ import annotations

import inspect
import os
from contextvars import ContextVar
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any, Protocol

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


_current_request: ContextVar[Request | None] = ContextVar(
    "prs_current_authorization_request", default=None
)
_provider_cache: "AuthorizationProvider | None" = None
_provider_cache_spec: str | None = None


@dataclass(slots=True)
class AuthorizationInput:
    """Data passed to an edition-specific authorization provider."""

    action: str
    request: Request | None = None
    connection: Any = None
    resource: dict[str, Any] | None = None
    subject: dict[str, Any] | None = None
    environment: dict[str, Any] | None = None
    payload: Any = None


@dataclass(slots=True)
class AuthorizationDecision:
    """Provider decision.

    ``allow=True`` is the community-edition default. Enterprise providers should
    return ``allow=False`` with a non-sensitive reason for denied requests.
    """

    allow: bool
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AuthorizationProvider(Protocol):
    """Interface implemented by free and paid-edition authorization providers."""

    async def authorize(self, data: AuthorizationInput) -> AuthorizationDecision:
        """Return allow/deny for the supplied action/resource context."""


class AllowAllAuthorizationProvider:
    """Default community-edition provider: keep existing open API behaviour."""

    async def authorize(self, data: AuthorizationInput) -> AuthorizationDecision:
        return AuthorizationDecision(allow=True)


class AuthorizationContextMiddleware(BaseHTTPMiddleware):
    """Store the current request in a context variable for service methods."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        token = _current_request.set(request)
        try:
            return await call_next(request)
        finally:
            _current_request.reset(token)


def get_current_request() -> Request | None:
    """Return the FastAPI request currently handled in this asyncio context."""

    return _current_request.get()


def reset_authorization_provider_cache() -> None:
    """Reset provider cache.

    This is primarily useful for tests and for long-running developer sessions
    where ``PRS_AUTH_PROVIDER`` is changed without restarting the interpreter.
    """

    global _provider_cache, _provider_cache_spec
    _provider_cache = None
    _provider_cache_spec = None


def _load_provider_from_spec(spec: str) -> AuthorizationProvider:
    """Load ``module:attribute`` provider from ``PRS_AUTH_PROVIDER``."""

    module_name, sep, attr_name = spec.partition(":")
    if not sep or not module_name or not attr_name:
        raise ValueError(
            "PRS_AUTH_PROVIDER must have format 'module:attribute', "
            f"got {spec!r}."
        )

    module = import_module(module_name)
    obj = getattr(module, attr_name)

    if inspect.isclass(obj):
        obj = obj()
    elif callable(obj):
        obj = obj()

    authorize = getattr(obj, "authorize", None)
    if not callable(authorize):
        raise TypeError(
            "Authorization provider must be an object with async "
            f"'authorize(data)' method, got {obj!r}."
        )

    return obj


def get_authorization_provider() -> AuthorizationProvider:
    """Return configured provider or the permissive community default."""

    global _provider_cache, _provider_cache_spec

    spec = os.getenv("PRS_AUTH_PROVIDER", "").strip()
    if _provider_cache is not None and spec == _provider_cache_spec:
        return _provider_cache

    if spec:
        provider = _load_provider_from_spec(spec)
    else:
        provider = AllowAllAuthorizationProvider()

    _provider_cache = provider
    _provider_cache_spec = spec
    return provider


async def authorize_action(
    action: str,
    *,
    request: Request | None = None,
    connection: Any = None,
    resource: dict[str, Any] | None = None,
    subject: dict[str, Any] | None = None,
    environment: dict[str, Any] | None = None,
    payload: Any = None,
) -> AuthorizationDecision:
    """Authorize an API action and raise HTTP 403 on denial."""

    data = AuthorizationInput(
        action=action,
        request=request or get_current_request(),
        connection=connection,
        resource=resource,
        subject=subject,
        environment=environment,
        payload=payload,
    )
    decision = await get_authorization_provider().authorize(data)
    if not decision.allow:
        raise HTTPException(
            status_code=403,
            detail=decision.reason or "Доступ запрещён политикой безопасности.",
        )
    return decision

