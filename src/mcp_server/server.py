import json
import os
from typing import Any, Literal, Mapping, Sequence, Tuple

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
            "enable_v2": ENABLE_V2,
        }
    )


@mcp.tool
async def peresvet_openapi() -> dict[str, Any]:
    """Fetch Peresvet OpenAPI schema (`/openapi.json`).

    Note: this endpoint may return 500 in some deployments; it is not required for CRUD tools.
    """
    return await _request("GET", "/openapi.json")


def _extract_created_id(resp: dict[str, Any]) -> str | None:
    if not resp.get("ok"):
        return None
    data = resp.get("data")
    if isinstance(data, dict):
        v = data.get("id")
        if isinstance(v, str) and v.strip():
            return v
    return None


def _as_str_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    return [str(v)]

def _bool_str(v: Any) -> str:
    return "true" if bool(v) else "false"

def _add_list(params: list[tuple[str, str]], key: str, values: Any) -> None:
    for x in _as_str_list(values):
        if x is None:
            continue
        s = str(x)
        if s.strip() == "":
            continue
        params.append((key, s))

def _crud_query_to_params(query: dict[str, Any]) -> list[tuple[str, str]]:
    """Convert legacy `q` dict into normal query params (no `q=`)."""
    params: list[tuple[str, str]] = []
    if "id" in query and query["id"] is not None:
        _add_list(params, "id", query["id"])
    if "base" in query and query["base"] is not None:
        params.append(("base", str(query["base"])))
    if "deref" in query and query["deref"] is not None:
        params.append(("deref", _bool_str(query["deref"])))
    if "scope" in query and query["scope"] is not None:
        params.append(("scope", str(query["scope"])))
    if "hierarchy" in query and query["hierarchy"] is not None:
        params.append(("hierarchy", _bool_str(query["hierarchy"])))
    if "getParent" in query and query["getParent"] is not None:
        params.append(("getParent", _bool_str(query["getParent"])))
    if "attributes" in query and query["attributes"] is not None:
        _add_list(params, "attributes", query["attributes"])
    if "filter" in query and query["filter"] is not None:
        params.append(("filter", json.dumps(query["filter"], ensure_ascii=False)))

    # entity-specific flags used by some endpoints
    for k in ("getLinkedTags", "getLinkedAlerts"):
        if k in query and query[k] is not None:
            params.append((k, _bool_str(query[k])))

    return params

def _query_value_to_str(value: Any) -> str:
    if isinstance(value, bool):
        return _bool_str(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


_DATA_QUERY_KNOWN_KEYS = frozenset(
    {
        "tagId",
        "start",
        "finish",
        "maxCount",
        "count",
        "timeStep",
        "format",
        "actual",
        "value",
        "params",
        "allRecordsAsValue",
    }
)
_DATA_QUERY_BLOCKED_KEYS = frozenset({"evalContextTagId"})


def _data_query_to_params(query: dict[str, Any]) -> list[tuple[str, str]]:
    params: list[tuple[str, str]] = []
    if "tagId" in query and query["tagId"] is not None:
        _add_list(params, "tagId", query["tagId"])
    for k in ("start", "finish", "maxCount", "count", "timeStep", "format", "actual"):
        if k in query and query[k] is not None:
            params.append((k, _query_value_to_str(query[k])))
    if "value" in query and query["value"] is not None:
        params.append(("value", _query_value_to_str(query["value"])))
    if "params" in query and query["params"] is not None:
        params.append(("params", _query_value_to_str(query["params"])))
    for k, v in query.items():
        if k in _DATA_QUERY_KNOWN_KEYS or k in _DATA_QUERY_BLOCKED_KEYS or v is None:
            continue
        params.append((k, _query_value_to_str(v)))
    return params


def _method_parameter_payload(parameter: dict[str, Any]) -> dict[str, Any]:
    if "attributes" in parameter:
        return parameter
    attrs: dict[str, Any] = {}
    if "cn" in parameter:
        attrs["cn"] = parameter["cn"]
    if "description" in parameter:
        attrs["description"] = parameter["description"]
    if "prsIndex" in parameter:
        attrs["prsIndex"] = parameter["prsIndex"]
    elif "index" in parameter:
        attrs["prsIndex"] = parameter["index"]
    if "prsActive" in parameter:
        attrs["prsActive"] = parameter["prsActive"]
    if "prsJsonConfigString" in parameter:
        attrs["prsJsonConfigString"] = parameter["prsJsonConfigString"]
    elif "config" in parameter:
        attrs["prsJsonConfigString"] = parameter["config"]
    if isinstance(parameter.get("attrs"), dict):
        attrs.update(parameter["attrs"])
    return {"attributes": attrs}


def _operation_parameter_payload(parameter: dict[str, Any]) -> dict[str, Any]:
    if "attributes" in parameter:
        return parameter
    attrs: dict[str, Any] = {
        "cn": parameter.get("cn"),
        "prsJsonConfigString": parameter.get("prsJsonConfigString", parameter.get("config", {})),
    }
    if "description" in parameter:
        attrs["description"] = parameter["description"]
    if "prsActive" in parameter:
        attrs["prsActive"] = parameter["prsActive"]
    if isinstance(parameter.get("attrs"), dict):
        attrs.update(parameter["attrs"])
    return {"attributes": attrs}


def _tag_operation_payload(operation: dict[str, Any]) -> dict[str, Any]:
    if "attributes" in operation:
        op = dict(operation)
        op["parameters"] = [_operation_parameter_payload(p) for p in operation.get("parameters") or []]
        return op
    cfg = operation.get("prsJsonConfigString")
    if cfg is None:
        cfg = {
            "query": operation.get("query"),
        }
        for key, out_key in (
            ("timeoutMs", "timeoutMs"),
            ("timeout_ms", "timeoutMs"),
            ("maxRows", "maxRows"),
            ("max_rows", "maxRows"),
            ("version", "version"),
        ):
            if key in operation and operation[key] is not None:
                cfg[out_key] = operation[key]
    attrs: dict[str, Any] = {
        "cn": operation.get("cn"),
        "prsEntityTypeCode": operation.get("prsEntityTypeCode", operation.get("kind", 0)),
        "prsJsonConfigString": cfg,
    }
    if "prsActive" in operation:
        attrs["prsActive"] = operation["prsActive"]
    if isinstance(operation.get("attrs"), dict):
        attrs.update(operation["attrs"])
    return {
        "attributes": attrs,
        "parameters": [_operation_parameter_payload(p) for p in operation.get("parameters") or []],
    }


def _linked_tag_payload(link: dict[str, Any]) -> dict[str, Any]:
    if "tagId" not in link:
        raise ValueError("linked tag item requires tagId")
    attrs = link.get("attributes")
    if attrs is None:
        attrs = {}
    return {
        "tagId": link["tagId"],
        "attributes": attrs,
        "operations": [_tag_operation_payload(op) for op in link.get("operations") or []],
    }


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

    This wraps `GET /v1/objects/?q=<json>`.

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
        ("hierarchy", _bool_str(hierarchy)),
        ("getParent", _bool_str(get_parent)),
    ]
    if base is not None:
        params.append(("base", base))
    if filter is not None:
        params.append(("filter", json.dumps(filter, ensure_ascii=False)))
    if attributes is not None:
        _add_list(params, "attributes", attributes)
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
    Wraps `GET /v1/tags/?q=<json>`.
    """
    params: list[tuple[str, str]] = [
        ("scope", str(scope)),
        ("hierarchy", _bool_str(hierarchy)),
        ("getParent", _bool_str(get_parent)),
    ]
    if base is not None:
        params.append(("base", base))
    if filter is not None:
        params.append(("filter", json.dumps(filter, ensure_ascii=False)))
    if attributes is not None:
        _add_list(params, "attributes", attributes)
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
            obj_id = _extract_created_id(resp)
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
                tag_id = _extract_created_id(resp)
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
    params = _crud_query_to_params(q)
    return await _request("GET", f"/v1/{entity}/", params=params)


@mcp.tool
async def peresvet_crud_create(entity: CrudEntity, payload: dict[str, Any]) -> dict[str, Any]:
    """Low-level create via POST `/v1/<entity>/`.

    Prefer the typed helpers for hierarchy entities:
    - `peresvet_object_create` / `peresvet_tag_create`
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
        payload["parameters"] = [_method_parameter_payload(p) for p in parameters]
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
        json_body={"sourceId": source_id, "parentId": parent_id},
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
    q = query or {}
    if "allRecordsAsValue" in q:
        params_obj = q.get("params")
        if not isinstance(params_obj, dict):
            params_obj = {}
        params_obj["allRecordsAsValue"] = q["allRecordsAsValue"]
        q["params"] = params_obj
    params = _data_query_to_params(q)
    return await _request("GET", "/v1/data/", params=params)


if ENABLE_V2:
    @mcp.tool
    async def peresvet_datastorages_v2_read(query: dict[str, Any] | None = None) -> dict[str, Any]:
        """Read dataStorages via `/v2/dataStorages/` (operations support).

        Use `getLinkedTags=true` to include tag links (with child `operations`
        for integrational links). Use `getLinkedAlerts=true` to include linked alerts.
        """
        q = query or {}
        params = _crud_query_to_params(q)
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
            "linkedTags": [_linked_tag_payload(link) for link in linked_tags or []],
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
            "linkedTags": [_linked_tag_payload(link) for link in linked_tags or []],
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
            "linkedTags": [_linked_tag_payload(link)],
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


def main() -> None:
    # Note: FastMCP HTTP transport serves MCP endpoint at `/mcp`.
    # SSE is legacy but kept for compatibility with existing setup.
    if MCP_TRANSPORT == "stdio":
        mcp.run()
    else:
        mcp.run(transport=MCP_TRANSPORT, host=MCP_HOST, port=MCP_PORT)


if __name__ == "__main__":
    main()

