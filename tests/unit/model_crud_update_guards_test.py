import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

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
