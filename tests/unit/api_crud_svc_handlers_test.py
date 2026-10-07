import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.common.api_crud_svc import (
    APICRUDSvc,
    ErrorHandler,
    NodeCreate,
    NodeDelete,
    NodeRead,
    coerce_prs_json_config_string_value,
    coerce_prs_json_strings_in_mapping_tree,
    valid_base,
    valid_uuid,
    valid_uuid_for_read,
)


def test_uuid_and_json_config_validators():
    uid = str(uuid4())
    assert valid_uuid(uid) == uid
    assert valid_uuid([uid]) == [uid]
    with pytest.raises(ValueError):
        valid_uuid("not-a-guid")
    assert valid_uuid_for_read("") == ""
    assert valid_uuid_for_read("  ") == ""
    assert valid_base(None) is None
    assert valid_base("  ") is None
    assert valid_base("prs") == "prs"
    assert valid_base(uid) == uid
    assert coerce_prs_json_config_string_value(None) is None
    assert coerce_prs_json_config_string_value({"a": 1}) == {"a": 1}
    assert coerce_prs_json_config_string_value("  ") is None
    assert coerce_prs_json_config_string_value('{"a": 1}') == {"a": 1}
    with pytest.raises(ValueError):
        coerce_prs_json_config_string_value("[1]")
    assert coerce_prs_json_config_string_value(5) == 5
    tree = {"prsJsonConfigString": '{"x": 1}', "child": [{"description": ""}]}
    coerce_prs_json_strings_in_mapping_tree(tree)
    assert tree["prsJsonConfigString"] == {"x": 1}
    assert tree["child"][0]["description"] is None


def test_error_handler_and_node_models():
    handler = ErrorHandler()
    asyncio.run(handler.handle_error(None))
    with pytest.raises(HTTPException) as ei:
        asyncio.run(handler.handle_error({"error": {"code": 424, "message": "x"}}))
    assert ei.value.status_code == 424
    uid = str(uuid4())
    created = NodeCreate.model_validate({"parentId": uid, "attributes": {"cn": "n", "prsJsonConfigString": '{"a":1}'}})
    assert created.attributes.prsJsonConfigString == {"a": 1}
    deleted = NodeDelete.model_validate({"id": uid})
    assert deleted.id == [uid]
    empty = NodeRead.model_validate({"id": ""})
    assert empty.id == ""


def test_api_crud_handlers():
    svc = object.__new__(APICRUDSvc)
    svc._config = SimpleNamespace(hierarchy={"class": "prsObject"}, svc_name="objects_api_crud")
    svc._logger = SimpleNamespace(exception=lambda *a, **k: None)
    svc._post_message = AsyncMock(return_value={"id": "n1"})
    uid = str(uuid4())
    payload = NodeCreate.model_validate({"parentId": uid, "attributes": {"cn": "n"}})
    assert asyncio.run(svc._create(payload)) == {"id": "n1"}
    read = NodeRead.model_validate({"id": uid})
    asyncio.run(svc._read(read))
    grafana = asyncio.run(svc._read(NodeRead.model_validate({"id": "", "attributes": ["cn"]})))
    assert grafana["data"][0]["id"] == ""
    asyncio.run(svc._update({"id": uid, "attributes": {"cn": "x"}}))
    asyncio.run(svc._delete(NodeDelete.model_validate({"id": uid})))
    res = asyncio.run(svc.api_get_read(NodeRead, "{", None))
    assert res["error"]["code"] == 500
    res = asyncio.run(svc.api_get_read(NodeRead, '{"id": "not-guid"}', None))
    assert res["error"]["code"] == 500
    ok = asyncio.run(svc.api_get_read(NodeRead, None, read))
    assert ok == {"id": "n1"}
    svc._set_handlers()
    assert "prsObject.api_crud_client.create.*" in svc._handlers
