import asyncio

from src.services.methods.method_catalog import (
    catalog_call_error,
    catalog_id_from_message,
    numeric_compatible,
    validate_method_message,
)
from src.services.methods.model_crud.methods_model_crud_svc import MethodsModelCRUD
from tests.unit.methods_model_crud_initiator_cache_test import _make_service


def test_legacy_method_without_catalog_stays_compatible():
    mes = {
        "parentId": "tag-1",
        "attributes": {"prsMethodAddress": "sum", "prsEntityTypeCode": 0},
        "initiatedBy": ["tag-2"],
        "parameters": [{"attributes": {"prsJsonConfigString": {"tagId": "tag-2"}, "prsIndex": 1}}],
    }
    assert validate_method_message(
        mes, placement="instance", catalog_id=None, catalog_address=None, require_address=False
    ) is None
    assert mes["attributes"]["prsMethodAddress"] == "sum"
    assert "prsCatalogMethodId" not in mes["attributes"]


def test_catalog_create_rejects_initiators_bad_type_and_blank_address():
    blank = {"attributes": {"prsMethodAddress": " "}, "initiatedBy": ["x"]}
    err = validate_method_message(
        blank, placement="catalog", catalog_id=None, catalog_address=None, require_address=True
    )
    assert err["error"]["code"] == 422

    typed = {"attributes": {"prsMethodAddress": "prs.stdlib.add", "prsEntityTypeCode": 1}}
    err = validate_method_message(
        typed, placement="catalog", catalog_id=None, catalog_address=None, require_address=True
    )
    assert err["error"]["code"] == 422

    linked = {
        "catalogMethodId": "other",
        "attributes": {"prsMethodAddress": "prs.stdlib.add", "prsCatalogMethodId": "other"},
    }
    err = validate_method_message(
        linked, placement="catalog", catalog_id="other", catalog_address="prs.stdlib.add", require_address=True
    )
    assert err["error"]["code"] == 422


def test_catalog_create_accepts_parameters_and_counts_types():
    mes = {
        "attributes": {"cn": "add", "prsMethodAddress": "prs.stdlib.add"},
        "parameters": [
            {"attributes": {"cn": "a", "prsIndex": 1, "prsValueTypeCode": 2}},
            {"attributes": {"cn": "b", "prsIndex": "2", "prsValueTypeCode": "2"}},
        ],
    }
    assert validate_method_message(
        mes, placement="catalog", catalog_id=None, catalog_address=None, require_address=True
    ) is None
    assert mes["attributes"]["prsEntityTypeCode"] == 0
    missing = {"attributes": {"prsMethodAddress": "prs.stdlib.add"}, "parameters": [{"attributes": {"cn": "a"}}]}
    assert validate_method_message(
        missing, placement="catalog", catalog_id=None, catalog_address=None, require_address=True
    )["error"]["code"] == 422


def test_instance_catalog_binding_allowlist_and_address_copy():
    mes = {
        "catalogMethodId": "cat-1",
        "attributes": {"prsMethodAddress": "copied", "prsEntityTypeCode": 0},
        "parameters": [
            {"attributes": {"cn": "a", "prsIndex": 1, "prsJsonConfigString": {"binding": "tag", "tagId": "t1"}}},
            {
                "attributes": {
                    "cn": "b",
                    "prsIndex": 2,
                    "prsJsonConfigString": {"binding": "literal", "value": 2, "valueTypeCode": 2},
                }
            },
        ],
    }
    assert validate_method_message(
        mes,
        placement="instance",
        catalog_id="cat-1",
        catalog_address="prs.stdlib.add",
        require_address=False,
    ) is None
    assert mes["attributes"]["prsMethodAddress"] == "prs.stdlib.add"
    assert mes["attributes"]["prsCatalogMethodId"] == "cat-1"

    routed = {
        "attributes": {"prsCatalogMethodId": "cat-1"},
        "parameters": [
            {"attributes": {"prsJsonConfigString": {"tagId": "t1", "routingKey": "prsTag.app_api_client.data_get.*"}}}
        ],
    }
    assert validate_method_message(
        routed, placement="instance", catalog_id="cat-1", catalog_address="prs.stdlib.add"
    ) is None
    assert catalog_id_from_message({"catalogMethodId": "a", "attributes": {"prsCatalogMethodId": "b"}})[1]["error"]["code"] == 422


def test_catalog_call_checks_arity_and_numeric_codes():
    catalog = [
        {"index": 1, "valueTypeCode": 2, "cn": "a"},
        {"index": 2, "valueTypeCode": 1, "cn": "b"},
    ]
    assert catalog_call_error(catalog, [{"index": 1, "data": 1.5}])
    assert catalog_call_error(
        catalog,
        [{"index": 1, "data": {"data": [{"data": [[0, 1.5, None]]}]}}, {"index": 2, "data": 1.2}],
    )
    assert catalog_call_error(
        catalog,
        [{"index": 1, "data": 1}, {"index": 2, "data": 2}],
    ) is None
    assert numeric_compatible(2, None) is False
    assert numeric_compatible(3, None) is True
    assert numeric_compatible(1, 2.0) is True


def test_delete_referenced_catalog_method_returns_409_and_folder_crud():
    class Hierarchy:
        def __init__(self):
            self.deleted = []
            self.added = []

        async def search(self, payload):
            filt = payload.get("filter") or {}
            if filt.get("prsCatalogMethodId") == ["cat-1"]:
                return [("inst", None, {"cn": ["use"]})]
            if payload.get("base") == "folder" and filt.get("objectClass") == ["prsMethod"]:
                return [("cat-1", None, {"cn": ["add"]})]
            return []

        async def get_node_class(self, node_id):
            return {"cat-1": "prsMethod", "tag-1": "prsTag"}.get(node_id, "prsModelNode")

        async def get_parent(self, node_id):
            return "root", None

        async def add(self, parent, attrs):
            self.added.append((parent, attrs))
            return "folder-new"

        async def delete(self, node_id):
            self.deleted.append(node_id)

        async def modify(self, node_id, attrs):
            return None

        async def move(self, node_id, parent):
            return None

    hierarchy = Hierarchy()
    svc = _make_service(hierarchy)
    svc._config.hierarchy["node_id"] = "root"
    blocked = asyncio.run(MethodsModelCRUD._delete(svc, {"id": "cat-1"}))
    assert blocked["error"]["code"] == 409
    assert hierarchy.deleted == []

    folder_blocked = asyncio.run(MethodsModelCRUD._folder_delete(svc, {"id": "folder"}))
    assert folder_blocked["error"]["code"] == 409
    assert hierarchy.deleted == []

    created = asyncio.run(MethodsModelCRUD._folder_create(svc, {"attributes": {"cn": "stdlib"}}))
    assert created["id"] == "folder-new"
    assert hierarchy.added[0][0] == "root"
    assert hierarchy.added[0][1]["objectClass"] == ["prsModelNode"]
    rejected = asyncio.run(MethodsModelCRUD._folder_create(svc, {"parentId": "tag-1", "attributes": {"cn": "x"}}))
    assert rejected["error"]["code"] == 422


def test_folder_read_drops_method_subclass_matches():
    class Hierarchy:
        async def search(self, payload):
            assert payload["filter"]["objectClass"] == ["prsModelNode"]
            assert "objectClass" in payload["attributes"]
            return [
                ("stdlib", None, {"cn": ["stdlib"], "objectClass": ["prsModelNode"]}),
                ("add", None, {"cn": ["add"], "objectClass": ["prsMethod"]}),
            ]

    svc = _make_service(Hierarchy())
    svc._config.hierarchy["node_id"] = "root"
    result = asyncio.run(MethodsModelCRUD._folder_read(svc, {"base": "root"}))
    assert [row["id"] for row in result["data"]] == ["stdlib"]


def test_prepare_copies_live_catalog_address_for_tag_instance():
    class Hierarchy:
        async def get_parent(self, node_id):
            if node_id == "cat-1":
                return "root", None
            return "tag-1", None

        async def get_node_class(self, node_id):
            return {"cat-1": "prsMethod", "tag-1": "prsTag"}.get(node_id, "prsModelNode")

        async def search(self, payload):
            if payload.get("id") == "cat-1":
                return [("cat-1", None, {"prsMethodAddress": ["prs.stdlib.add"]})]
            return []

    svc = _make_service(Hierarchy())
    svc._config.hierarchy["node_id"] = "root"
    mes = {
        "parentId": "tag-1",
        "catalogMethodId": "cat-1",
        "attributes": {"prsMethodAddress": "copied"},
        "parameters": [
            {"attributes": {"cn": "a", "prsIndex": 1, "prsJsonConfigString": {"binding": "tag", "tagId": "left"}}},
            {"attributes": {"cn": "b", "prsIndex": 2, "prsJsonConfigString": {"binding": "literal", "value": 1, "valueTypeCode": 2}}},
        ],
    }
    assert asyncio.run(MethodsModelCRUD._prepare_method_write(svc, mes, creating=True)) is None
    assert mes["attributes"]["prsMethodAddress"] == "prs.stdlib.add"
    missing = asyncio.run(
        MethodsModelCRUD._prepare_method_write(
            svc,
            {"parentId": "tag-1", "catalogMethodId": "missing", "attributes": {}},
            creating=True,
        )
    )
    assert missing["error"]["code"] == 422
