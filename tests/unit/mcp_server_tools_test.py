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
            await _unwrap(mcp_server.peresvet_method_create)(
                cn="from-catalog",
                parent_id="p",
                method_address="placeholder",
                catalog_method_id="cat-1",
            )
            await _unwrap(mcp_server.peresvet_method_folder_create)(cn="stdlib", description="arith")
            await _unwrap(mcp_server.peresvet_method_folders_list)(base="root", scope=2, filter={"cn": ["stdlib"]})
            await _unwrap(mcp_server.peresvet_method_folder_update)(folder_id="f1", cn="renamed")
            await _unwrap(mcp_server.peresvet_method_folder_delete)(folder_id=["f1"])
            await _unwrap(mcp_server.peresvet_method_description_import)(
                yaml_text="folders: []",
                parent_id="methods",
                probe=True,
            )
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
            await _unwrap(mcp_server.peresvet_connector_services)()
            await _unwrap(mcp_server.peresvet_connector_service_log_tail)(services=["methods_app"], limit=10)
            await _unwrap(mcp_server.peresvet_connector_service_log_clear)(services=["methods_app"])
            await _unwrap(mcp_server.peresvet_ptz)(tag_id="cam")
            await _unwrap(mcp_server.peresvet_ptz)(tag_id="cam", action="move", pan=1, tilt=0, zoom=0)

    asyncio.run(run())
    paths = [c[1] for c in captured]
    assert "/openapi.json" in paths
    assert "/v1/objects/" in paths
    assert "/v1/tags/copy" in paths
    catalog_calls = [
        item for item in captured
        if item[1].endswith("/methods/") and item[3] and item[3].get("catalogMethodId") == "cat-1"
    ]
    assert catalog_calls
    assert catalog_calls[0][3]["attributes"]["prsCatalogMethodId"] == "cat-1"
    assert catalog_calls[0][3]["attributes"]["prsMethodAddress"] == "placeholder"
    folder_create = next(item for item in captured if item[1] == "/v1/methods/folders" and item[0] == "POST")
    assert folder_create[3]["attributes"]["cn"] == "stdlib"
    description = next(item for item in captured if item[1] == "/v1/methods/description")
    assert description[3] == {"yaml": "folders: []", "probe": True}
    assert "parentId" not in description[3]
    status = next(item for item in captured if item[1] == "/v1/ptz/" and item[0] == "GET")
    assert ("tagId", "cam") in status[2]
    move = next(item for item in captured if item[1] == "/v1/ptz/" and item[0] == "POST")
    assert move[3]["action"] == "move"
    assert move[3]["pan"] == 1
    services = next(item for item in captured if item[1] == "/v1/connectors_app/services")
    assert services[0] == "GET"
    log_tail = next(item for item in captured if item[1] == "/v1/connectors_app/service_log_tail" and item[0] == "GET")
    assert ("service", "methods_app") in log_tail[2]
    assert ("limit", "10") in log_tail[2]
