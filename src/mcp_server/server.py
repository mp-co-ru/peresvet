import json
import os
from typing import Any, Literal

import aiohttp
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse


CrudEntity = Literal[
    "objects",
    "tags",
    "alerts",
    "methods",
    "connectors",
    "schedules",
    "dataStorages",
]


def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return default if v is None or v == "" else v


PERESVET_BASE_URL = _env("PERESVET_BASE_URL", "http://one_app:8000").rstrip("/")
PERESVET_TIMEOUT_SECONDS = float(_env("PERESVET_TIMEOUT_SECONDS", "15"))

def _normalize_transport(v: str) -> str:
    """
    Normalize MCP transport names across client/server ecosystems.

    Notes:
    - Many modern MCP clients expect Streamable HTTP (POST to `/mcp`).
    - Some configs use `streamable_http` / `streamable-http` naming.
    """
    x = (v or "").strip().lower()
    if x in {"", "default"}:
        return "http"
    if x in {"stdio"}:
        return "stdio"
    if x in {"sse"}:
        return "sse"
    if x in {"http", "streamable_http", "streamable-http", "streamablehttp"}:
        return "http"
    return x


MCP_TRANSPORT = _normalize_transport(_env("MCP_PERESVET_TRANSPORT", "http"))
MCP_HOST = _env("MCP_PERESVET_HOST", "0.0.0.0")
MCP_PORT = int(_env("MCP_PERESVET_PORT", "8000"))


mcp = FastMCP(name="Peresvet")


async def _request(
    method: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
    json_body: Any | None = None,
) -> dict[str, Any]:
    url = f"{PERESVET_BASE_URL}{path}"
    timeout = aiohttp.ClientTimeout(total=PERESVET_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.request(method, url, params=params, json=json_body) as resp:
            text = await resp.text()
            try:
                payload = json.loads(text) if text else None
            except Exception:
                payload = text
            ok = 200 <= resp.status < 300
            return {
                "ok": ok,
                "status": resp.status,
                "url": str(resp.url),
                "data": payload,
            }


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")


@mcp.custom_route("/config", methods=["GET"])
async def config(_: Request) -> JSONResponse:
    return JSONResponse(
        {
            "peresvet_base_url": PERESVET_BASE_URL,
            "timeout_seconds": PERESVET_TIMEOUT_SECONDS,
            "transport": MCP_TRANSPORT,
            "host": MCP_HOST,
            "port": MCP_PORT,
        }
    )


@mcp.tool
async def peresvet_openapi() -> dict[str, Any]:
    """Fetch Peresvet OpenAPI schema (`/openapi.json`)."""
    return await _request("GET", "/openapi.json")


@mcp.tool
async def peresvet_crud_read(entity: CrudEntity, query: dict[str, Any]) -> dict[str, Any]:
    """Read entities via `/v1/<entity>/?q=<json>`."""
    return await _request("GET", f"/v1/{entity}/", params={"q": json.dumps(query, ensure_ascii=False)})


@mcp.tool
async def peresvet_crud_create(entity: CrudEntity, payload: dict[str, Any]) -> dict[str, Any]:
    """Create an entity via POST `/v1/<entity>/`."""
    return await _request("POST", f"/v1/{entity}/", json_body=payload)


@mcp.tool
async def peresvet_crud_update(entity: CrudEntity, payload: dict[str, Any]) -> dict[str, Any]:
    """Update an entity via PUT `/v1/<entity>/`."""
    return await _request("PUT", f"/v1/{entity}/", json_body=payload)


@mcp.tool
async def peresvet_crud_delete(entity: CrudEntity, payload: dict[str, Any]) -> dict[str, Any]:
    """Delete an entity via DELETE `/v1/<entity>/`."""
    return await _request("DELETE", f"/v1/{entity}/", json_body=payload)


@mcp.tool
async def peresvet_data_get(query: dict[str, Any]) -> dict[str, Any]:
    """Read historical tag data via GET `/v1/data/?q=<json>`."""
    return await _request("GET", "/v1/data/", params={"q": json.dumps(query, ensure_ascii=False)})


@mcp.tool
async def peresvet_data_set(payload: dict[str, Any]) -> dict[str, Any]:
    """Write historical tag data via POST `/v1/data/`."""
    return await _request("POST", "/v1/data/", json_body=payload)


def main() -> None:
    # Note: FastMCP HTTP transport serves MCP endpoint at `/mcp`.
    # SSE is legacy but kept for compatibility with existing setup.
    if MCP_TRANSPORT == "stdio":
        mcp.run()
    else:
        mcp.run(transport=MCP_TRANSPORT, host=MCP_HOST, port=MCP_PORT)


if __name__ == "__main__":
    main()

