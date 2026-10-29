import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.common.api_crud_svc import OneNodeInReadResult
from src.common.model_crud_svc import ModelCRUDSvc
from src.services.objects.model_crud.objects_model_crud_svc import ObjectsModelCRUD


class _Logger:
    def error(self, *a, **k):
        pass

    def debug(self, *a, **k):
        pass


def test_model_crud_update_rejects_missing_and_wrong_class():
    svc = object.__new__(ModelCRUDSvc)
    svc._config = SimpleNamespace(svc_name="objects_model_crud", hierarchy={"class": "prsObject"})
    svc._logger = _Logger()
    svc._hierarchy = SimpleNamespace(
        does_node_exist=AsyncMock(return_value=False),
        get_node_class=AsyncMock(return_value="prsTag"),
    )
    missing = asyncio.run(svc._update({"id": "n1"}))
    assert missing["error"]["code"] == 422
    svc._hierarchy.does_node_exist = AsyncMock(return_value=True)
    wrong = asyncio.run(svc._update({"id": "n1"}))
    assert "необрабатываемый класс" in wrong["error"]["message"]


def test_update_rejects_parent_of_wrong_class():
    svc = object.__new__(ModelCRUDSvc)
    svc._config = SimpleNamespace(
        svc_name="tags_model_crud",
        hierarchy={
            "class": "prsTag",
            "node_id": "tags-root",
            "parent_classes": ["prsObject", "prsFolder"],
        },
    )
    svc._logger = _Logger()

    async def exists(_node_id):
        return True

    svc._hierarchy = SimpleNamespace(
        does_node_exist=exists,
        get_node_class=AsyncMock(side_effect=lambda node_id: "prsTag" if node_id == "tag-1" else "prsConnector"),
        search=AsyncMock(return_value=[]),
    )
    rejected = asyncio.run(svc._update({"id": "tag-1", "parentId": "connector-1"}))
    assert rejected["error"]["code"] == 422
    assert "родитель" in rejected["error"]["message"]


def test_objects_copy_subtree_requires_ids_and_delegates():
    svc = object.__new__(ObjectsModelCRUD)
    svc._hierarchy = object()
    svc._post_message = AsyncMock()
    bad = asyncio.run(svc._copy_subtree({"sourceId": "s"}))
    assert bad["error"]["code"] == 422

    async def fake_copy(*args, **kwargs):
        assert kwargs["expected_root_class"] == "prsObject"
        assert kwargs["new_root_cn"] == "copy"
        return {"id": "new"}

    import src.common.model_copy as model_copy
    orig = model_copy.copy_subtree_rooted_at
    model_copy.copy_subtree_rooted_at = fake_copy
    try:
        ok = asyncio.run(
            svc._copy_subtree({"sourceId": "s", "parentId": "p", "attributes": {"cn": "copy"}})
        )
    finally:
        model_copy.copy_subtree_rooted_at = orig
    assert ok == {"id": "new"}
    svc._config = SimpleNamespace(hierarchy={"class": "prsObject"})
    svc._handlers = {}
    ObjectsModelCRUD._set_handlers(svc)
    assert "prsObject.api_crud.copy" in svc._handlers


def test_read_result_includes_node_dn():
    svc = object.__new__(ModelCRUDSvc)
    svc._config = SimpleNamespace(
        svc_name="methods_model_crud",
        hierarchy={"class": "prsMethod", "node": "methods", "node_id": "root"},
    )
    svc._logger = _Logger()
    dn = "cn=Новый метод,cn=C,cn=objects,cn=prs"

    async def search(_payload):
        return [("method-1", dn, {"cn": ["Новый метод"]})]

    svc._hierarchy = SimpleNamespace(search=search)

    async def further_read(_mes, result):
        return result

    svc._further_read = further_read
    result = asyncio.run(
        svc._read(
            {
                "id": "method-1",
                "base": None,
                "hierarchy": False,
                "scope": 0,
                "filter": {},
            }
        )
    )
    assert result["data"][0]["dn"] == dn
    parsed = OneNodeInReadResult.model_validate(result["data"][0])
    assert parsed.model_dump()["dn"] == dn
