"""Pure helpers for Peresvet MCP tools (no FastMCP import)."""

from __future__ import annotations

import json
from typing import Any


def extract_created_id(resp: dict[str, Any]) -> str | None:
    if not resp.get("ok"):
        return None
    data = resp.get("data")
    if isinstance(data, dict):
        v = data.get("id")
        if isinstance(v, str) and v.strip():
            return v
    return None


def as_str_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    return [str(v)]


def bool_str(v: Any) -> str:
    return "true" if bool(v) else "false"


def add_list(params: list[tuple[str, str]], key: str, values: Any) -> None:
    for x in as_str_list(values):
        if x is None:
            continue
        s = str(x)
        if s.strip() == "":
            continue
        params.append((key, s))


def crud_query_to_params(query: dict[str, Any]) -> list[tuple[str, str]]:
    """Convert a CRUD filter dict into normal query params (no ``q=``)."""
    params: list[tuple[str, str]] = []
    if "id" in query and query["id"] is not None:
        add_list(params, "id", query["id"])
    if "base" in query and query["base"] is not None:
        params.append(("base", str(query["base"])))
    if "deref" in query and query["deref"] is not None:
        params.append(("deref", bool_str(query["deref"])))
    if "scope" in query and query["scope"] is not None:
        params.append(("scope", str(query["scope"])))
    if "hierarchy" in query and query["hierarchy"] is not None:
        params.append(("hierarchy", bool_str(query["hierarchy"])))
    if "getParent" in query and query["getParent"] is not None:
        params.append(("getParent", bool_str(query["getParent"])))
    if "attributes" in query and query["attributes"] is not None:
        add_list(params, "attributes", query["attributes"])
    if "filter" in query and query["filter"] is not None:
        params.append(("filter", json.dumps(query["filter"], ensure_ascii=False)))

    for k in ("getLinkedTags", "getLinkedAlerts"):
        if k in query and query[k] is not None:
            params.append((k, bool_str(query[k])))

    return params


def query_value_to_str(value: Any) -> str:
    if isinstance(value, bool):
        return bool_str(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


DATA_QUERY_KNOWN_KEYS = frozenset(
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
DATA_QUERY_BLOCKED_KEYS = frozenset({"evalContextTagId"})


def data_query_to_params(query: dict[str, Any]) -> list[tuple[str, str]]:
    params: list[tuple[str, str]] = []
    if "tagId" in query and query["tagId"] is not None:
        add_list(params, "tagId", query["tagId"])
    for k in ("start", "finish", "maxCount", "count", "timeStep", "format", "actual"):
        if k in query and query[k] is not None:
            params.append((k, query_value_to_str(query[k])))
    if "value" in query and query["value"] is not None:
        params.append(("value", query_value_to_str(query["value"])))
    if "params" in query and query["params"] is not None:
        params.append(("params", query_value_to_str(query["params"])))
    for k, v in query.items():
        if k in DATA_QUERY_KNOWN_KEYS or k in DATA_QUERY_BLOCKED_KEYS or v is None:
            continue
        params.append((k, query_value_to_str(v)))
    return params


def prepare_data_query(query: dict[str, Any] | None) -> list[tuple[str, str]]:
    q = dict(query or {})
    if "allRecordsAsValue" in q:
        params_obj = q.get("params")
        if not isinstance(params_obj, dict):
            params_obj = {}
        else:
            params_obj = dict(params_obj)
        params_obj["allRecordsAsValue"] = q["allRecordsAsValue"]
        q["params"] = params_obj
    return data_query_to_params(q)


def alarms_query_to_params(query: dict[str, Any]) -> list[tuple[str, str]]:
    params: list[tuple[str, str]] = []
    if "parentId" in query and query["parentId"] is not None:
        add_list(params, "parentId", query["parentId"])
    for k in ("getChildren", "format", "fired"):
        if k in query and query[k] is not None:
            params.append((k, bool_str(query[k])))
    return params


def method_parameter_payload(parameter: dict[str, Any]) -> dict[str, Any]:
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


def operation_parameter_payload(parameter: dict[str, Any]) -> dict[str, Any]:
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


def tag_operation_payload(operation: dict[str, Any]) -> dict[str, Any]:
    if "attributes" in operation:
        op = dict(operation)
        op["parameters"] = [operation_parameter_payload(p) for p in operation.get("parameters") or []]
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
        "parameters": [operation_parameter_payload(p) for p in operation.get("parameters") or []],
    }


def linked_tag_payload(link: dict[str, Any]) -> dict[str, Any]:
    if "tagId" not in link:
        raise ValueError("linked tag item requires tagId")
    attrs = link.get("attributes")
    if attrs is None:
        attrs = {}
    return {
        "tagId": link["tagId"],
        "attributes": attrs,
        "operations": [tag_operation_payload(op) for op in link.get("operations") or []],
    }


def copy_payload(
    *,
    source_id: str,
    parent_id: str | None = None,
    attributes: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"sourceId": source_id}
    if parent_id is not None:
        body["parentId"] = parent_id
    if attributes:
        body["attributes"] = attributes
    if extra:
        body.update(extra)
    return body


def alert_create_payload(
    *,
    parent_id: str,
    cn: str | None = None,
    description: str | None = None,
    value: Any = 10,
    high: bool = True,
    auto_ack: bool = True,
    attrs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    attributes: dict[str, Any] = {
        "prsJsonConfigString": {
            "value": value,
            "high": high,
            "autoAck": auto_ack,
        }
    }
    if cn is not None:
        attributes["cn"] = cn
    if description is not None:
        attributes["description"] = description
    if attrs:
        extra_attrs = dict(attrs)
        extra_cfg = extra_attrs.pop("prsJsonConfigString", None)
        attributes.update(extra_attrs)
        if isinstance(extra_cfg, dict):
            attributes["prsJsonConfigString"].update(extra_cfg)
    return {"parentId": parent_id, "attributes": attributes}


def schedule_create_payload(
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
    cfg: dict[str, Any] = {
        "interval_type": interval_type,
        "interval_value": interval_value,
    }
    if start is not None:
        cfg["start"] = start
    if end is not None:
        cfg["end"] = end
    attributes: dict[str, Any] = {"prsJsonConfigString": cfg}
    if cn is not None:
        attributes["cn"] = cn
    if description is not None:
        attributes["description"] = description
    if attrs:
        extra_attrs = dict(attrs)
        extra_cfg = extra_attrs.pop("prsJsonConfigString", None)
        attributes.update(extra_attrs)
        if isinstance(extra_cfg, dict):
            attributes["prsJsonConfigString"].update(extra_cfg)
    payload: dict[str, Any] = {"attributes": attributes}
    if parent_id is not None:
        payload["parentId"] = parent_id
    return payload


def connector_linked_tag_payload(link: dict[str, Any]) -> dict[str, Any]:
    if "tagId" not in link:
        raise ValueError("linked tag item requires tagId")
    if "attributes" in link:
        return {"tagId": link["tagId"], "attributes": link["attributes"]}
    cfg = link.get("prsJsonConfigString")
    if cfg is None:
        cfg = link.get("config")
    if cfg is None:
        cfg = {}
    else:
        cfg = dict(cfg)
    if "source" in link and "source" not in cfg:
        cfg["source"] = link["source"]
    for key in ("maxDev", "JSONata", "frequency"):
        if key in link and key not in cfg:
            cfg[key] = link[key]
    attrs: dict[str, Any] = {"prsJsonConfigString": cfg}
    if "cn" in link:
        attrs["cn"] = link["cn"]
    if "description" in link:
        attrs["description"] = link["description"]
    if isinstance(link.get("attrs"), dict):
        attrs.update(link["attrs"])
    return {"tagId": link["tagId"], "attributes": attrs}


def connector_create_payload(
    *,
    cn: str | None = None,
    parent_id: str | None = None,
    description: str | None = None,
    config: dict[str, Any] | None = None,
    linked_tags: list[dict[str, Any]] | None = None,
    attrs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    attributes: dict[str, Any] = {
        "prsJsonConfigString": dict(config or {}),
    }
    if cn is not None:
        attributes["cn"] = cn
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
        "linkedTags": [connector_linked_tag_payload(link) for link in linked_tags or []],
    }
    if parent_id is not None:
        payload["parentId"] = parent_id
    return payload


def connector_update_payload(
    *,
    connector_id: str,
    cn: str | None = None,
    description: str | None = None,
    config: dict[str, Any] | None = None,
    linked_tags: list[dict[str, Any]] | None = None,
    unlink_tags: list[str] | None = None,
    attrs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    attributes: dict[str, Any] = {}
    if cn is not None:
        attributes["cn"] = cn
    if description is not None:
        attributes["description"] = description
    if config is not None:
        attributes["prsJsonConfigString"] = dict(config)
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
    payload: dict[str, Any] = {"id": connector_id}
    if attributes:
        payload["attributes"] = attributes
    if linked_tags is not None:
        payload["linkedTags"] = [connector_linked_tag_payload(link) for link in linked_tags]
    if unlink_tags is not None:
        payload["unlinkTags"] = unlink_tags
    return payload


def auth_headers(bearer_token: str | None) -> dict[str, str]:
    token = (bearer_token or "").strip()
    if not token:
        return {}
    if token.lower().startswith("bearer "):
        return {"Authorization": token}
    return {"Authorization": f"Bearer {token}"}
