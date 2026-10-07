import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import patch

if "fastmcp" not in sys.modules:
    try:
        import fastmcp  # noqa: F401
    except ModuleNotFoundError:
        class _FastMCP:
            def __init__(self, name):
                self.name = name

            def custom_route(self, *args, **kwargs):
                def deco(fn):
                    return fn
                return deco

            def tool(self, fn=None, **kwargs):
                if fn is None:
                    return lambda f: f
                return fn

        sys.modules["fastmcp"] = SimpleNamespace(FastMCP=_FastMCP)

from src.mcp_server import server as mcp_server
from src.mcp_server.payloads import as_str_list, bool_str, query_value_to_str, tag_operation_payload


def test_env_bool_and_transport_helpers():
    assert mcp_server._env_bool("MISSING_FLAG_XYZ", True) is True
    assert mcp_server._normalize_transport("") == "http"
    assert mcp_server._normalize_transport("default") == "http"
    assert mcp_server._normalize_transport("stdio") == "stdio"
    assert mcp_server._normalize_transport("sse") == "sse"
    assert mcp_server._normalize_transport("streamable-http") == "http"
    assert mcp_server._normalize_transport("other") == "other"
    assert as_str_list(None) == []
    assert as_str_list("a") == ["a"]
    assert bool_str(0) == "false"
    assert query_value_to_str(True) == "true"
    assert '"a"' in query_value_to_str({"a": 1})
    op = tag_operation_payload({"cn": "q", "query": "select 1", "timeout_ms": 5, "max_rows": 10})
    assert op["attributes"]["prsJsonConfigString"]["timeoutMs"] == 5


def _unwrap(obj):
    for attr in ("fn", "func", "__wrapped__"):
        inner = getattr(obj, attr, None)
        if callable(inner):
            return inner
    return obj


def test_mcp_tools_call_http_layer():
    captured = []

    async def fake_request(method, path, *, params=None, json_body=None):
        captured.append((method, path, params, json_body))
        if path.endswith("/objects/") and method == "GET":
            return {"ok": True, "data": {"data": [{"id": "obj-1"}]}}
        if path.endswith("/tags/") and method == "GET":
            return {"ok": True, "data": {"data": [{"id": "tag-1"}]}}
        return {"ok": True, "status": 200, "data": {"id": "n1"}}

    async def run():
        with patch.object(mcp_server, "_request", fake_request):
            health = await _unwrap(mcp_server.health)(None)
            assert health.body == b"OK"
            cfg = await _unwrap(mcp_server.config)(None)
            assert b"peresvet_base_url" in cfg.body
            await _unwrap(mcp_server.peresvet_openapi)()
            await _unwrap(mcp_server.peresvet_objects_list)(base="root", attributes=["cn"], filter={"cn": ["a"]})
            await _unwrap(mcp_server.peresvet_objects_tree)(base="root")
            await _unwrap(mcp_server.peresvet_object_create)(cn="pump", parent_id="p", description="d")
            child = await _unwrap(mcp_server.peresvet_object_get_child_id)(parent_id="p", cn="pump")
            assert child["data"]["id"] == "obj-1"
            await _unwrap(mcp_server.peresvet_tag_get_child_id)(parent_id="p", cn="tag")
            await _unwrap(mcp_server.peresvet_tags_list)(base="root")
            await _unwrap(mcp_server.peresvet_tag_create)(cn="t", parent_id="p")
            await _unwrap(mcp_server.peresvet_crud_read)(entity="objects", query={"id": ["a"]})
            await _unwrap(mcp_server.peresvet_crud_create)(entity="objects", payload={"attributes": {"cn": "x"}})
            await _unwrap(mcp_server.peresvet_crud_update)(entity="objects", payload={"id": "a"})
            await _unwrap(mcp_server.peresvet_crud_delete)(entity="objects", payload={"id": "a"})
            await _unwrap(mcp_server.peresvet_method_create)(cn="m", parent_id="p", method_address="pkg.fn")
            await _unwrap(mcp_server.peresvet_virtual_method_create)(tag_id="t", method_address="pkg.fn")
            await _unwrap(mcp_server.peresvet_object_copy)(source_id="s", parent_id="p")
            await _unwrap(mcp_server.peresvet_tag_copy)(source_id="s", parent_id="p")
            await _unwrap(mcp_server.peresvet_alert_copy)(source_id="s", parent_id="p")
            await _unwrap(mcp_server.peresvet_alert_create)(parent_id="t")
            await _unwrap(mcp_server.peresvet_alarms_get)(parent_id="o")
            await _unwrap(mcp_server.peresvet_alarm_ack)(alarm_id="a", x=1)
            await _unwrap(mcp_server.peresvet_schedule_create)(cn="s", start="2026-01-01T00:00:00")
            await _unwrap(mcp_server.peresvet_data_get)(query={"tagId": "t1"})
            await _unwrap(mcp_server.peresvet_data_set)(payload={"data": []})
            await _unwrap(mcp_server.peresvet_connector_create)(cn="c")
            await _unwrap(mcp_server.peresvet_connector_update)(connector_id="c1")
            await _unwrap(mcp_server.peresvet_connector_copy)(source_id="c1")
            await _unwrap(mcp_server.peresvet_apply_hierarchy)(
                root_parent_id="p", tree=[{"cn": "obj", "tags": [{"cn": "t"}]}]
            )

    asyncio.run(run())
    paths = [c[1] for c in captured]
    assert "/openapi.json" in paths
    assert "/v1/objects/" in paths
    assert "/v1/tags/copy" in paths
