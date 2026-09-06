import json
import os
from typing import Any, Literal, Mapping, Sequence, Tuple

import aiohttp
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

from .payloads import (
    add_list,
    alert_create_payload,
    alarms_query_to_params,
    auth_headers,
    bool_str,
    connector_create_payload,
    connector_update_payload,
    copy_payload,
    crud_query_to_params,
    extract_created_id,
    linked_tag_payload,
    method_parameter_payload,
    prepare_data_query,
    schedule_create_payload,
)


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
PERESVET_BEARER_TOKEN = _env("PERESVET_BEARER_TOKEN", "")

def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    x = v.strip().lower()
    if x in {"1", "true", "yes", "on"}:
        return True
    if x in {"0", "false", "no", "off"}:
        return False
    return default

# v2 MCP tools are optional
_mcp_enable_v2_raw = os.getenv("MCP_PERESVET_ENABLE_V2")
if _mcp_enable_v2_raw is None or _mcp_enable_v2_raw.strip() == "":
    ENABLE_V2 = _env_bool("PRS_ENABLE_V2", False)
else:
    ENABLE_V2 = _env_bool("MCP_PERESVET_ENABLE_V2", False)

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
    params: Mapping[str, str] | Sequence[Tuple[str, str]] | None = None,
    json_body: Any | None = None,
) -> dict[str, Any]:
    url = f"{PERESVET_BASE_URL}{path}"
    timeout = aiohttp.ClientTimeout(total=PERESVET_TIMEOUT_SECONDS)
    headers = auth_headers(PERESVET_BEARER_TOKEN)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.request(
            method, url, params=params, json=json_body, headers=headers or None
        ) as resp:
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
            "enable_v2": ENABLE_V2,
            "auth_configured": bool(PERESVET_BEARER_TOKEN.strip()),
        }
    )


@mcp.tool
async def peresvet_openapi() -> dict[str, Any]:
    """Fetch Peresvet OpenAPI schema (`/openapi.json`).

    Note: this endpoint may return 500 in some deployments; it is not required for CRUD tools.
    """
    return await _request("GET", "/openapi.json")


async def _find_child_by_cn(entity: Literal["objects", "tags"], *, parent_id: str, cn: str) -> str | None:
    """Find a direct child by `cn` under a given parent id. Returns node id or None."""
    params = [
        ("base", parent_id),
        ("scope", "1"),
        ("filter", json.dumps({"cn": [cn]}, ensure_ascii=False)),
        ("attributes", "cn"),
    ]
    resp = await _request("GET", f"/v1/{entity}/", params=params)
    if not resp.get("ok"):
        return None
    data = resp.get("data")
    if not isinstance(data, dict):
        return None
    items = data.get("data")
    if not isinstance(items, list) or not items:
        return None
    first = items[0]
    if isinstance(first, dict) and isinstance(first.get("id"), str):
        return first["id"]
    return None


@mcp.tool
async def peresvet_objects_list(
    *,
    base: str | None = None,
    scope: int = 1,
    attributes: list[str] | None = None,
    filter: dict[str, list[Any]] | None = None,
    hierarchy: bool = False,
    get_parent: bool = False,
) -> dict[str, Any]:
    """List objects from Peresvet hierarchy.

    This wraps `GET /v1/objects/` with ordinary query params.

    Key hierarchy concepts in Peresvet:
    - `base`: id (UUID) or DN of the *base node* where search starts. If omitted, search starts from root.
    - `scope`:
      - 0: only the `base` node
      - 1: direct children of `base` (default)
      - 2: whole subtree from `base`
    - `hierarchy=true`: return nodes with nested `children` in response (when supported by backend).
    - `get_parent=true`: include `parentId` in each node.
    """
    params: list[tuple[str, str]] = [
        ("scope", str(scope)),
        ("hierarchy", bool_str(hierarchy)),
        ("getParent", bool_str(get_parent)),
    ]
    if base is not None:
        params.append(("base", base))
    if filter is not None:
        params.append(("filter", json.dumps(filter, ensure_ascii=False)))
    if attributes is not None:
        add_list(params, "attributes", attributes)
    return await _request("GET", "/v1/objects/", params=params)

@mcp.tool
async def peresvet_objects_tree(*, base: str | None = None) -> dict[str, Any]:
    """Get objects as a tree (nested `children`).

    Equivalent to `peresvet_objects_list(scope=2, hierarchy=True, get_parent=True)`.
    """
    return await peresvet_objects_list(base=base, scope=2, hierarchy=True, get_parent=True)


@mcp.tool
async def peresvet_object_create(
    *,
    cn: str,
    parent_id: str | None = None,
    description: str | None = None,
    attrs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create an object node, optionally under a parent.

    This wraps `POST /v1/objects/`.

    - `cn`: object name (required).
    - `parent_id`: UUID of parent node. If omitted, object is created under the entity's base node.
      This is the crucial field for building a tree (otherwise you'll get a "flat" list at root).
    - `attrs`: extra node attributes (e.g. `prsActive`, `prsDefault`, `prsIndex`, `prsJsonConfigString`, ...).
    """
    attributes: dict[str, Any] = {"cn": cn}
    if description is not None:
        attributes["description"] = description
    if attrs:
        attributes.update(attrs)
    payload: dict[str, Any] = {"attributes": attributes}
    if parent_id is not None:
        payload["parentId"] = parent_id
    return await _request("POST", "/v1/objects/", json_body=payload)

@mcp.tool
async def peresvet_object_get_child_id(*, parent_id: str, cn: str) -> dict[str, Any]:
    """Get child object id by name under `parent_id` (scope=1).

    Useful for building hierarchies: find parent's children by `cn` before creating.
    """
    found = await _find_child_by_cn("objects", parent_id=parent_id, cn=cn)
    return {"ok": True, "status": 200, "url": "", "data": {"id": found}}


@mcp.tool
async def peresvet_tag_get_child_id(*, parent_id: str, cn: str) -> dict[str, Any]:
    """Get child tag id by name under `parent_id` (scope=1)."""
    found = await _find_child_by_cn("tags", parent_id=parent_id, cn=cn)
    return {"ok": True, "status": 200, "url": "", "data": {"id": found}}


@mcp.tool
async def peresvet_tags_list(
    *,
    base: str | None = None,
    scope: int = 1,
    attributes: list[str] | None = None,
    filter: dict[str, list[Any]] | None = None,
    hierarchy: bool = False,
    get_parent: bool = False,
) -> dict[str, Any]:
    """List tags from Peresvet hierarchy.

    Same query semantics as `peresvet_objects_list`, but for tags.
    Wraps `GET /v1/tags/`.
    """
    params: list[tuple[str, str]] = [
        ("scope", str(scope)),
        ("hierarchy", bool_str(hierarchy)),
        ("getParent", bool_str(get_parent)),
    ]
    if base is not None:
        params.append(("base", base))
    if filter is not None:
        params.append(("filter", json.dumps(filter, ensure_ascii=False)))
    if attributes is not None:
        add_list(params, "attributes", attributes)
    return await _request("GET", "/v1/tags/", params=params)

@mcp.tool
async def peresvet_tags_tree(*, base: str | None = None) -> dict[str, Any]:
    """Get tags as a tree (nested `children`)."""
    return await peresvet_tags_list(base=base, scope=2, hierarchy=True, get_parent=True)


@mcp.tool
async def peresvet_tag_create(
    *,
    cn: str,
    parent_id: str,
    description: str | None = None,
    value_type_code: int = 1,
    default_value: Any | None = None,
    measure_units: str | None = None,
    attrs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a tag under an object node.

    Wraps `POST /v1/tags/`.

    - `parent_id`: UUID of parent node (required for correct hierarchy).
    - `value_type_code`: 0 int | 1 float | 2 string | 3 discrete | 4 json | 5 table.
    """
    attributes: dict[str, Any] = {"cn": cn, "prsValueTypeCode": value_type_code}
    if description is not None:
        attributes["description"] = description
    if default_value is not None:
        attributes["prsDefaultValue"] = default_value
    if measure_units is not None:
        attributes["prsMeasureUnits"] = measure_units
    if attrs:
        attributes.update(attrs)
    payload: dict[str, Any] = {"parentId": parent_id, "attributes": attributes}
    return await _request("POST", "/v1/tags/", json_body=payload)


@mcp.tool
async def peresvet_apply_hierarchy(
    *,
    root_parent_id: str,
    tree: list[dict[str, Any]],
    idempotent: bool = True,
    continue_on_error: bool = True,
) -> dict[str, Any]:
    """Create objects (and optional tags) from a nested tree definition.

    This tool is designed for LLMs to avoid hierarchy mistakes with `parentId` / `base`.

    Input format (`tree`) is a list of nodes:

    - **Object node**
      - `cn` (str, required)
      - `description` (str, optional)
      - `attrs` (dict, optional) extra object attributes
      - `tags` (list, optional): each tag is `{cn, description?, value_type_code?, default_value?, measure_units?, attrs?}`
      - `children` (list, optional): nested object nodes

    Behavior:
    - Objects are created under `root_parent_id` (and then under created parents).
    - Tags are created under the object they belong to (using tag `parentId`).
    - If `idempotent=true`, the tool tries to re-use existing children with the same `cn`
      under the same parent (scope=1) instead of creating duplicates.
    """

    created_objects: list[dict[str, Any]] = []
    created_tags: list[dict[str, Any]] = []
    reused: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    async def _apply_object_node(node: dict[str, Any], parent_id: str, path: str) -> str | None:
        cn = node.get("cn")
        if not isinstance(cn, str) or not cn.strip():
            errors.append({"path": path, "error": "object.cn is required"})
            return None

        obj_id: str | None = None
        if idempotent:
            obj_id = await _find_child_by_cn("objects", parent_id=parent_id, cn=cn)
            if obj_id:
                reused.append({"kind": "object", "path": path, "id": obj_id, "cn": cn, "parent_id": parent_id})

        if not obj_id:
            resp = await peresvet_object_create(
                cn=cn,
                parent_id=parent_id,
                description=node.get("description"),
                attrs=node.get("attrs") if isinstance(node.get("attrs"), dict) else None,
            )
            obj_id = extract_created_id(resp)
            if not obj_id:
                errors.append({"kind": "object", "path": path, "cn": cn, "parent_id": parent_id, "resp": resp})
                return None
            created_objects.append({"path": path, "id": obj_id, "cn": cn, "parent_id": parent_id})

        # tags under this object
        for i, tag in enumerate(node.get("tags") or []):
            if not isinstance(tag, dict):
                errors.append({"kind": "tag", "path": f"{path}.tags[{i}]", "error": "tag must be an object"})
                if not continue_on_error:
                    return obj_id
                continue
            tcn = tag.get("cn")
            if not isinstance(tcn, str) or not tcn.strip():
                errors.append({"kind": "tag", "path": f"{path}.tags[{i}]", "error": "tag.cn is required"})
                if not continue_on_error:
                    return obj_id
                continue

            tag_id: str | None = None
            if idempotent:
                tag_id = await _find_child_by_cn("tags", parent_id=obj_id, cn=tcn)
                if tag_id:
                    reused.append({"kind": "tag", "path": f"{path}.tags[{i}]", "id": tag_id, "cn": tcn, "parent_id": obj_id})

            if not tag_id:
                resp = await peresvet_tag_create(
                    cn=tcn,
                    parent_id=obj_id,
                    description=tag.get("description"),
                    value_type_code=int(tag.get("value_type_code", 1)),
                    default_value=tag.get("default_value"),
                    measure_units=tag.get("measure_units"),
                    attrs=tag.get("attrs") if isinstance(tag.get("attrs"), dict) else None,
                )
                tag_id = extract_created_id(resp)
                if not tag_id:
                    errors.append({"kind": "tag", "path": f"{path}.tags[{i}]", "cn": tcn, "parent_id": obj_id, "resp": resp})
                    if not continue_on_error:
                        return obj_id
                    continue
                created_tags.append({"path": f"{path}.tags[{i}]", "id": tag_id, "cn": tcn, "parent_id": obj_id})

        # children
        for i, child in enumerate(node.get("children") or []):
            if not isinstance(child, dict):
                errors.append({"kind": "object", "path": f"{path}.children[{i}]", "error": "child must be an object"})
                if not continue_on_error:
                    return obj_id
                continue
            child_id = await _apply_object_node(child, obj_id, f"{path}.children[{i}]")
            if child_id is None and not continue_on_error:
                return obj_id

        return obj_id

    for i, node in enumerate(tree):
        if not isinstance(node, dict):
            errors.append({"kind": "object", "path": f"tree[{i}]", "error": "node must be an object"})
            if not continue_on_error:
                break
            continue
        await _apply_object_node(node, root_parent_id, f"tree[{i}]")
        if errors and not continue_on_error:
            break

    ok = len(errors) == 0
    return {
        "ok": ok,
        "status": 200 if ok else 207,
        "url": "",
        "data": {
            "created_objects": created_objects,
            "created_tags": created_tags,
            "reused": reused,
            "errors": errors,
        },
    }


@mcp.tool
async def peresvet_crud_read(entity: CrudEntity, query: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read entities via `/v1/<entity>/` using normal query params.

    If `query` is omitted, an empty filter `{}` is used.
    """
    q = query or {}
    params = crud_query_to_params(q)
    return await _request("GET", f"/v1/{entity}/", params=params)


@mcp.tool
async def peresvet_crud_create(entity: CrudEntity, payload: dict[str, Any]) -> dict[str, Any]:
    """Low-level create via POST `/v1/<entity>/`.

    Prefer the typed helpers for hierarchy entities:
    - `peresvet_object_create` / `peresvet_tag_create` / `peresvet_alert_create`
    - `peresvet_connector_create` / `peresvet_schedule_create`
    - or `peresvet_apply_hierarchy` to create whole trees safely.
    """
    return await _request("POST", f"/v1/{entity}/", json_body=payload)


@mcp.tool
async def peresvet_crud_update(entity: CrudEntity, payload: dict[str, Any]) -> dict[str, Any]:
    """Low-level update via PUT `/v1/<entity>/`."""
    return await _request("PUT", f"/v1/{entity}/", json_body=payload)


@mcp.tool
async def peresvet_crud_delete(entity: CrudEntity, payload: dict[str, Any]) -> dict[str, Any]:
    """Low-level delete via DELETE `/v1/<entity>/`."""
    return await _request("DELETE", f"/v1/{entity}/", json_body=payload)


@mcp.tool
async def peresvet_method_create(
    *,
    parent_id: str,
    method_address: str,
    cn: str | None = None,
    description: str | None = None,
    entity_type_code: int = 0,
    initiated_by: str | list[str] | None = None,
    parameters: list[dict[str, Any]] | None = None,
    attrs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a Peresvet method under a tag or alert.

    Wraps `POST /v1/methods/`.

    - `entity_type_code=0`: calculated method, triggered by `initiated_by`, writes result to tag data.
    - `entity_type_code=1`: virtual method, called on `GET /v1/data/` and returns tag data without historian read.
    - `parameters[].config` / `parameters[].prsJsonConfigString` supports:
      `routingKey` + `message` + optional `responseJsonata`, `clientJsonata`,
      or legacy nested data get with `tagId`.
    """
    attributes: dict[str, Any] = {
        "prsMethodAddress": method_address,
        "prsEntityTypeCode": entity_type_code,
    }
    if cn is not None:
        attributes["cn"] = cn
    if description is not None:
        attributes["description"] = description
    if attrs:
        attributes.update(attrs)
    payload: dict[str, Any] = {
        "parentId": parent_id,
        "attributes": attributes,
    }
    if initiated_by is not None:
        payload["initiatedBy"] = initiated_by
    if parameters is not None:
        payload["parameters"] = [method_parameter_payload(p) for p in parameters]
    return await _request("POST", "/v1/methods/", json_body=payload)


@mcp.tool
async def peresvet_virtual_method_create(
    *,
    tag_id: str,
    method_address: str,
    cn: str | None = None,
    description: str | None = None,
    parameters: list[dict[str, Any]] | None = None,
    attrs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a virtual method (`prsEntityTypeCode=1`) for a tag.

    The method is executed when `peresvet_data_get` reads `tag_id`. Its return
    value becomes the tag value at the request `finish` timestamp.

    Use `parameters[].config.clientJsonata` to pass data from the user's
    `peresvet_data_get(query=...)` request, including arbitrary top-level keys.
    """
    return await peresvet_method_create(
        parent_id=tag_id,
        method_address=method_address,
        cn=cn,
        description=description,
        entity_type_code=1,
        initiated_by=None,
        parameters=parameters,
        attrs=attrs,
    )


@mcp.tool
async def peresvet_method_copy(*, source_id: str, parent_id: str) -> dict[str, Any]:
    """Copy an existing method to a new tag/alert parent.

    Wraps `POST /v1/methods/copy`.
    """
    return await _request(
        "POST",
        "/v1/methods/copy",
        json_body=copy_payload(source_id=source_id, parent_id=parent_id),
    )


@mcp.tool
async def peresvet_object_copy(
    *,
    source_id: str,
    parent_id: str,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy an object and its subtree (tags, alerts, methods).

    Wraps `POST /v1/objects/copy`. Internal references are rewritten;
    references to nodes outside the copied subtree are kept.
    """
    return await _request(
        "POST",
        "/v1/objects/copy",
        json_body=copy_payload(source_id=source_id, parent_id=parent_id, attributes=attributes),
    )


@mcp.tool
async def peresvet_tag_copy(
    *,
    source_id: str,
    parent_id: str,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy a tag (and attached alerts/methods) under a new parent.

    Wraps `POST /v1/tags/copy`.
    """
    return await _request(
        "POST",
        "/v1/tags/copy",
        json_body=copy_payload(source_id=source_id, parent_id=parent_id, attributes=attributes),
    )


@mcp.tool
async def peresvet_alert_copy(
    *,
    source_id: str,
    parent_id: str,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy an alert to another tag parent.

    Wraps `POST /v1/alerts/copy`.
    """
    return await _request(
        "POST",
        "/v1/alerts/copy",
        json_body=copy_payload(source_id=source_id, parent_id=parent_id, attributes=attributes),
    )


@mcp.tool
async def peresvet_alert_create(
    *,
    parent_id: str,
    cn: str | None = None,
    description: str | None = None,
    value: Any = 10,
    high: bool = True,
    auto_ack: bool = True,
    attrs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create an alert under a tag.

    Wraps `POST /v1/alerts/`.

    - `parent_id`: tag UUID.
    - `value`: threshold stored in `prsJsonConfigString.value`.
    - `high=true`: fire when tag value >= `value`; otherwise when tag value < `value`.
    - `auto_ack`: auto-acknowledge when the condition clears.
    """
    return await _request(
        "POST",
        "/v1/alerts/",
        json_body=alert_create_payload(
            parent_id=parent_id,
            cn=cn,
            description=description,
            value=value,
            high=high,
            auto_ack=auto_ack,
            attrs=attrs,
        ),
    )


@mcp.tool
async def peresvet_alarms_get(
    *,
    parent_id: str | list[str] | None = None,
    get_children: bool = False,
    format_ts: bool = False,
    fired: bool = True,
) -> dict[str, Any]:
    """Read active (or unacked inactive) alarms.

    Wraps `GET /v1/alarms/`.

    - `parent_id`: object UUID or list of object UUIDs.
    - `get_children=true`: include alarms of child objects.
    - `fired=true`: only currently active alarms.
    """
    query: dict[str, Any] = {
        "getChildren": get_children,
        "format": format_ts,
        "fired": fired,
    }
    if parent_id is not None:
        query["parentId"] = parent_id
    return await _request("GET", "/v1/alarms/", params=alarms_query_to_params(query))


@mcp.tool
async def peresvet_alarm_ack(*, alarm_id: str, x: int | str | None = None) -> dict[str, Any]:
    """Acknowledge an alarm.

    Wraps `PUT /v1/alarms/`. `x` is the ack timestamp (ISO8601 or microseconds);
    omit it to use the platform current time.
    """
    payload: dict[str, Any] = {"id": alarm_id}
    if x is not None:
        payload["x"] = x
    return await _request("PUT", "/v1/alarms/", json_body=payload)


@mcp.tool
async def peresvet_connector_create(
    *,
    cn: str | None = None,
    parent_id: str | None = None,
    description: str | None = None,
    config: dict[str, Any] | None = None,
    linked_tags: list[dict[str, Any]] | None = None,
    attrs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a connector, optionally with tag links.

    Wraps `POST /v1/connectors/`.

    - `config` is stored as `prsJsonConfigString` (MQTT/broker settings depend on connector type).
    - `linked_tags[]` items need `tagId` and either `attributes` or compact
      `source` / `config` / `maxDev` / `JSONata` / `frequency`.
    """
    return await _request(
        "POST",
        "/v1/connectors/",
        json_body=connector_create_payload(
            cn=cn,
            parent_id=parent_id,
            description=description,
            config=config,
            linked_tags=linked_tags,
            attrs=attrs,
        ),
    )


@mcp.tool
async def peresvet_connector_update(
    *,
    connector_id: str,
    cn: str | None = None,
    description: str | None = None,
    config: dict[str, Any] | None = None,
    linked_tags: list[dict[str, Any]] | None = None,
    unlink_tags: list[str] | None = None,
    attrs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update a connector and its tag links.

    Wraps `PUT /v1/connectors/`. Use `unlink_tags` to detach tags.
    """
    return await _request(
        "PUT",
        "/v1/connectors/",
        json_body=connector_update_payload(
            connector_id=connector_id,
            cn=cn,
            description=description,
            config=config,
            linked_tags=linked_tags,
            unlink_tags=unlink_tags,
            attrs=attrs,
        ),
    )


@mcp.tool
async def peresvet_connector_copy(
    *,
    source_id: str,
    copy_linked_tags: bool = False,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy a connector. Optionally copy tag links.

    Wraps `POST /v1/connectors/` with `sourceId` (there is no `/copy` route).
    """
    return await _request(
        "POST",
        "/v1/connectors/",
        json_body=copy_payload(
            source_id=source_id,
            attributes=attributes,
            extra={"copyLinkedTags": copy_linked_tags},
        ),
    )


@mcp.tool
async def peresvet_connector_command(*, connector_id: str, command: dict[str, Any]) -> dict[str, Any]:
    """Send a remote command to a connector over MQTT.

    Wraps `POST /v1/connectors_app/`.

    Typical `command` keys:
    - `lines`: shell lines executed on the connector host;
    - `timeoutSec`, `maxOutputBytes`, `logToPlatform`.
    Results appear in `peresvet_connector_command_output_tail`.
    """
    return await _request(
        "POST",
        "/v1/connectors_app/",
        json_body={"id": connector_id, "command": command},
    )


@mcp.tool
async def peresvet_connector_link_status(*, connector_id: str) -> dict[str, Any]:
    """MQTT link status of a connector (`mqttConnected`).

    Wraps `GET /v1/connectors_app/link_status`.
    """
    return await _request(
        "GET",
        "/v1/connectors_app/link_status",
        params=[("id", connector_id)],
    )


@mcp.tool
async def peresvet_connector_log_tail(*, connector_id: str) -> dict[str, Any]:
    """Recent connector log lines received over MQTT.

    Wraps `GET /v1/connectors_app/log_tail`.
    """
    return await _request(
        "GET",
        "/v1/connectors_app/log_tail",
        params=[("id", connector_id)],
    )


@mcp.tool
async def peresvet_connector_command_output_tail(*, connector_id: str) -> dict[str, Any]:
    """Recent remote command output (`prsConnector.command_output`).

    Wraps `GET /v1/connectors_app/command_output_tail`.
    """
    return await _request(
        "GET",
        "/v1/connectors_app/command_output_tail",
        params=[("id", connector_id)],
    )


@mcp.tool
async def peresvet_schedule_create(
    *,
    cn: str | None = None,
    parent_id: str | None = None,
    description: str | None = None,
    start: str | None = None,
    interval_type: str = "hours",
    interval_value: int = 1,
    end: str | None = None,
    attrs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a schedule.

    Wraps `POST /v1/schedules/`.

    - `interval_type`: `seconds` | `minutes` | `hours` | `days`.
    - `start` / `end`: ISO8601 timestamps.
    """
    return await _request(
        "POST",
        "/v1/schedules/",
        json_body=schedule_create_payload(
            cn=cn,
            parent_id=parent_id,
            description=description,
            start=start,
            interval_type=interval_type,
            interval_value=interval_value,
            end=end,
            attrs=attrs,
        ),
    )


@mcp.tool
async def peresvet_data_get(query: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read tag data via GET `/v1/data/` using normal query params.

    If `query` is omitted, an empty filter `{}` is used.

    Data points are returned as arrays in the order: `[x, y, q]`
    where `x` is timestamp (microseconds), `y` is value, `q` is quality.

    The backend can return data from historian, an integrational dataStorage,
    or a virtual method (`prsEntityTypeCode=1`) attached to the tag.

    Virtual method options:
    - arbitrary top-level query keys are forwarded to `/v1/data/` and become
      part of the virtual method `clientRequest` for `clientJsonata` parameters.
      Example: `{"tagId": "...", "calendarTagId": "...", "finish": "..."}`.

    Advanced options for integrational tabular tags:
    - `query.params` (dict): extra options forwarded to `/v1/data`.
      Example: `{"operation": "selectByCalendar", "allRecordsAsValue": false}`.
    - convenience key `query.allRecordsAsValue` is auto-mapped to
      `query.params.allRecordsAsValue`.
    """
    return await _request("GET", "/v1/data/", params=prepare_data_query(query))


if ENABLE_V2:
    @mcp.tool
    async def peresvet_datastorages_v2_read(query: dict[str, Any] | None = None) -> dict[str, Any]:
        """Read dataStorages via `/v2/dataStorages/` (operations support).

        Use `getLinkedTags=true` to include tag links (with child `operations`
        for integrational links). Use `getLinkedAlerts=true` to include linked alerts.
        """
        q = query or {}
        params = crud_query_to_params(q)
        return await _request("GET", "/v2/dataStorages/", params=params)

    @mcp.tool
    async def peresvet_datastorages_v2_create(payload: dict[str, Any]) -> dict[str, Any]:
        """Create dataStorage via POST `/v2/dataStorages/`.

        Notes for integrational relational storage (`prsEntityTypeCode=2`):
        - Operations are passed as child nodes of tag link:
          `linkedTags[].operations[]`.
        - Operation attributes live in `linkedTags[].operations[].attributes`
          (including `cn`, `prsEntityTypeCode`, `prsJsonConfigString`).
        - SQL params mapping is defined in operation parameters as
          `linkedTags[].operations[].parameters[].attributes.prsJsonConfigString.JSONata`.
        """
        return await _request("POST", "/v2/dataStorages/", json_body=payload)

    @mcp.tool
    async def peresvet_integrational_datastorage_create(
        *,
        cn: str,
        dsn: str,
        description: str | None = None,
        parent_id: str | None = None,
        linked_tags: list[dict[str, Any]] | None = None,
        attrs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create an integrational relational dataStorage (`prsEntityTypeCode=2`).

        Wraps `POST /v2/dataStorages/`.

        - `dsn`: asyncpg/PostgreSQL DSN stored in `prsJsonConfigString.dsn`.
        - `linked_tags[]`: items with `tagId`, optional `attributes`, and
          `operations[]`.
        - `operations[].prsEntityTypeCode`: 0 GET, 1 SET.
        - `operations[].query`: SQL with named params like `:start`.
        - `operations[].parameters[]`: items with `cn` and `config.JSONata`.
        """
        attributes: dict[str, Any] = {
            "cn": cn,
            "prsEntityTypeCode": 2,
            "prsJsonConfigString": {"dsn": dsn},
        }
        if description is not None:
            attributes["description"] = description
        if attrs:
            extra_attrs = dict(attrs)
            extra_cfg = extra_attrs.pop("prsJsonConfigString", None)
            attributes.update(extra_attrs)
            if isinstance(extra_cfg, dict):
                attributes["prsJsonConfigString"].update(extra_cfg)

        payload: dict[str, Any] = {
            "attributes": attributes,
            "linkedTags": [linked_tag_payload(link) for link in linked_tags or []],
        }
        if parent_id is not None:
            payload["parentId"] = parent_id
        return await _request("POST", "/v2/dataStorages/", json_body=payload)

    @mcp.tool
    async def peresvet_datastorages_v2_update(payload: dict[str, Any]) -> dict[str, Any]:
        """Update dataStorage via PUT `/v2/dataStorages/`.

        For integrational relational setup use:
        - `linkedTags` to attach/update tag link configuration and child `operations`;
        - `unlinkTags` to detach tags.
        """
        return await _request("PUT", "/v2/dataStorages/", json_body=payload)

    @mcp.tool
    async def peresvet_integrational_datastorage_update(
        *,
        datastorage_id: str,
        cn: str | None = None,
        dsn: str | None = None,
        description: str | None = None,
        linked_tags: list[dict[str, Any]] | None = None,
        unlink_tags: list[str] | None = None,
        attrs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update an integrational relational dataStorage and its tag operations.

        Wraps `PUT /v2/dataStorages/`. Passing `linked_tags` replaces operations
        for the specified tag links according to the v2 backend contract.
        """
        attributes: dict[str, Any] = {}
        if cn is not None:
            attributes["cn"] = cn
        if description is not None:
            attributes["description"] = description
        if dsn is not None:
            attributes["prsJsonConfigString"] = {"dsn": dsn}
        if attrs:
            extra_attrs = dict(attrs)
            extra_cfg = extra_attrs.pop("prsJsonConfigString", None)
            attributes.update(extra_attrs)
            if isinstance(extra_cfg, dict):
                cfg = attributes.get("prsJsonConfigString")
                if not isinstance(cfg, dict):
                    cfg = {}
                cfg.update(extra_cfg)
                attributes["prsJsonConfigString"] = cfg

        payload: dict[str, Any] = {
            "id": datastorage_id,
            "linkedTags": [linked_tag_payload(link) for link in linked_tags or []],
        }
        if attributes:
            payload["attributes"] = attributes
        if unlink_tags is not None:
            payload["unlinkTags"] = unlink_tags
        return await _request("PUT", "/v2/dataStorages/", json_body=payload)

    @mcp.tool
    async def peresvet_integrational_tag_operations_update(
        *,
        datastorage_id: str,
        tag_id: str,
        operations: list[dict[str, Any]],
        link_attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Replace GET/SET operations for one integrational tag link.

        `operations` accepts compact operation objects:
        `{"cn": "select", "prsEntityTypeCode": 0, "query": "...", "parameters": [{"cn": "start", "config": {"JSONata": "$.start"}}]}`.
        """
        link: dict[str, Any] = {
            "tagId": tag_id,
            "attributes": link_attributes or {},
            "operations": operations,
        }
        payload = {
            "id": datastorage_id,
            "linkedTags": [linked_tag_payload(link)],
        }
        return await _request("PUT", "/v2/dataStorages/", json_body=payload)


@mcp.tool
async def peresvet_data_set(payload: dict[str, Any]) -> dict[str, Any]:
    """Write historical tag data via POST `/v1/data/`.

    Data points must be arrays in the order: `[x, y, q]` (or shorter forms `[y]`, `[x, y]`).

    For integrational tabular tags, pass params per tag item:
    - `data[i].params.operation` = operation `cn`
    - other SQL values in `data[i].params.*`
    """
    return await _request("POST", "/v1/data/", json_body=payload)


@mcp.tool
async def peresvet_datafunc_get(query: dict[str, Any] | None = None) -> dict[str, Any]:
    """Aggregated tag data via GET `/v1/datafunc/`.

    Query keys match `peresvet_data_get` (`tagId`, `start`, `finish`, `timeStep`,
    `format`, extra client keys for virtual methods). Use this instead of
    `/v1/data/` when the client needs duration/code aggregations.
    """
    return await _request("GET", "/v1/datafunc/", params=prepare_data_query(query))


def main() -> None:
    # Note: FastMCP HTTP transport serves MCP endpoint at `/mcp`.
    # SSE is legacy but kept for compatibility with existing setup.
    if MCP_TRANSPORT == "stdio":
        mcp.run()
    else:
        mcp.run(transport=MCP_TRANSPORT, host=MCP_HOST, port=MCP_PORT)


if __name__ == "__main__":
    main()

