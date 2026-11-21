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


def test_catalog_definition_rejects_runtime_method_types():
    for code in (1, 2, 3, 4):
        err = validate_method_message(
            {"attributes": {"prsMethodAddress": "pkg.fn", "prsEntityTypeCode": code}},
            placement="catalog",
            catalog_id=None,
            catalog_address=None,
            require_address=True,
        )
        assert err["error"]["code"] == 422
        assert "должен быть 0" in err["error"]["message"]


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

    writer = {"attributes": {"prsMethodAddress": "pkg.write", "prsEntityTypeCode": 2}}
    action = {"attributes": {"prsMethodAddress": "pkg.act", "prsEntityTypeCode": 3}}
    write_action = {"attributes": {"prsMethodAddress": "pkg.onwrite", "prsEntityTypeCode": 4}}
    assert validate_method_message(
        action, placement="instance", catalog_id="cat", catalog_address="pkg.act", require_address=True
    ) is None
    assert validate_method_message(
        write_action, placement="instance", catalog_id="cat", catalog_address="pkg.onwrite", require_address=True
    ) is None
    assert validate_method_message(
        writer, placement="instance", catalog_id=None, catalog_address=None, require_address=False
    ) is None

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
    variadic = {
        "attributes": {"prsMethodAddress": "demo.sum_any", "prsVariadic": True},
        "parameters": [{"attributes": {"cn": "x", "prsIndex": 1}}],
    }
    assert validate_method_message(
        variadic, placement="catalog", catalog_id=None, catalog_address=None, require_address=True
    ) is None
    assert variadic["parameters"] == []
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
    ) is None
    assert catalog_call_error(
        catalog,
        [{"index": 1, "data": 1}, {"index": 2, "data": 2}],
    ) is None
    assert numeric_compatible(2, None) is False
    assert numeric_compatible(3, None) is True
    assert numeric_compatible(1, 2.0) is True


def test_further_read_loads_parameters_when_object_class_is_not_in_attributes():
    class Hierarchy:
        async def get_node_class(self, node_id):
            assert node_id == "method-1"
            return "prsMethod"

        async def get_node_dn(self, node_id):
            assert node_id == "method-1"
            return "cn=person_in_zone,cn=methods,cn=prs"

        async def get_parent(self, node_id):
            raise RuntimeError(node_id)

        async def search(self, payload):
            base = payload.get("base") or ""
            if base.startswith("cn=initiatedBy,"):
                return []
            if base.startswith("cn=parameters,"):
                return [(
                    "param-1",
                    "cn=zone,cn=parameters,cn=system,cn=person_in_zone,cn=methods,cn=prs",
                    {"cn": ["zone"], "prsIndex": ["2"], "prsValueTypeCode": ["4"]},
                )]
            raise AssertionError(payload)

    svc = _make_service(Hierarchy())
    result = asyncio.run(MethodsModelCRUD._further_read(svc, {}, {
        "data": [{"id": "method-1", "attributes": {"cn": ["person_in_zone"]}}]
    }))
    parameters = result["data"][0]["parameters"]
    assert len(parameters) == 1
    assert parameters[0]["attributes"]["cn"] == ["zone"]


def test_further_read_returns_a_folder_without_looking_up_method_children():
    class Hierarchy:
        async def search(self, payload):
            raise AssertionError(payload)

        async def get_node_dn(self, node_id):
            raise AssertionError(node_id)

    svc = _make_service(Hierarchy())
    result = asyncio.run(MethodsModelCRUD._further_read(svc, {}, {
        "data": [{
            "id": "folder-1",
            "attributes": {
                "cn": ["stdlib"],
                "objectClass": ["top", "prsModelNode", "prsFolder"],
            },
        }]
    }))
    assert result["data"][0]["id"] == "folder-1"
    assert "initiatedBy" not in result["data"][0]
    assert result["data"][0]["attributes"]["objectClass"][0] == "prsFolder"


def test_delete_referenced_catalog_method_returns_409_and_folder_crud():
    class Hierarchy:
        def __init__(self):
            self.deleted = []
            self.added = []

        async def search(self, payload):
            node_id = payload.get("id")
            if node_id == "root":
                return [("root", None, {"cn": ["methods"]})]
            if node_id == "prs-node":
                return [("prs-node", None, {"cn": ["prs"]})]
            filt = payload.get("filter") or {}
            if filt.get("prsCatalogMethodId") == ["cat-1"]:
                return [("inst", None, {"cn": ["use"]})]
            if payload.get("base") == "folder" and filt.get("objectClass") == ["prsMethod"]:
                return [("cat-1", None, {"cn": ["add"]})]
            return []

        async def get_node_class(self, node_id):
            return {"cat-1": "prsMethod", "tag-1": "prsTag"}.get(node_id, "prsModelNode")

        async def get_parent(self, node_id):
            if node_id == "root":
                return "prs-node", None
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
    assert hierarchy.added[0][1]["objectClass"] == ["prsFolder"]
    via_flag = asyncio.run(MethodsModelCRUD._create(svc, {
        "folder": True,
        "attributes": {"cn": "Видео", "description": "Методы видео"},
    }))
    assert via_flag["id"] == "folder-new"
    assert hierarchy.added[-1][1]["cn"] == "Видео"
    assert hierarchy.added[-1][1]["objectClass"] == ["prsFolder"]
    assert "prsMethodAddress" not in hierarchy.added[-1][1]
    rejected = asyncio.run(MethodsModelCRUD._folder_create(svc, {"parentId": "tag-1", "attributes": {"cn": "x"}}))
    assert rejected["error"]["code"] == 422


def test_folder_read_drops_method_subclass_matches():
    class Hierarchy:
        async def search(self, payload):
            assert payload["filter"]["objectClass"] == ["prsFolder"]
            assert "objectClass" in payload["attributes"]
            return [
                ("stdlib", None, {"cn": ["stdlib"], "objectClass": ["prsFolder"]}),
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


def test_variadic_instance_parameters_are_stored_without_type():
    class Hierarchy:
        async def search(self, payload):
            if payload.get("id") == "cat":
                return [("cat", None, {"prsVariadic": ["TRUE"]})]
            return []

    svc = object.__new__(MethodsModelCRUD)
    svc._hierarchy = Hierarchy()
    mes = {
        "catalogMethodId": "cat",
        "attributes": {},
        "parameters": [
            {"attributes": {"cn": "a", "prsIndex": 1, "prsValueTypeCode": 2}},
            {"attributes": {"cn": "b", "prsIndex": 2, "prsValueTypeCode": 3}},
        ],
    }
    asyncio.run(MethodsModelCRUD._variadic_parameter_policy(svc, mes))
    assert all("prsValueTypeCode" not in item["attributes"] for item in mes["parameters"])


class _AlertEventHierarchy:
    def __init__(self, classes):
        self.classes = classes
        self.added = []

    async def get_node_class(self, node_id):
        return self.classes.get(node_id, "prsTag")

    async def get_parent(self, node_id):
        return "tag-parent", None

    async def get_node_dn(self, node_id):
        return f"cn={node_id},cn=prs"

    async def search(self, payload):
        if payload.get("attributes") == ["prsActive"]:
            return [(payload.get("id"), None, {"prsActive": ["FALSE"]})]
        attrs = payload.get("attributes") or []
        if payload.get("id") and "objectClass" in attrs:
            node_id = payload.get("id")
            object_class = self.classes.get(node_id)
            if not object_class:
                return []
            return [(node_id, None, {"objectClass": ["top", "prsModelNode", object_class]})]
        cn = (payload.get("filter") or {}).get("cn")
        if cn == ["system"]:
            return [("system-node", None, {"cn": ["system"]})]
        return []

    async def add(self, parent, attrs):
        self.added.append((parent, dict(attrs)))
        return f"new-{len(self.added)}"


def _link_attrs(hierarchy, cn):
    return [attrs for _, attrs in hierarchy.added if attrs.get("cn") == [cn]]


def test_alert_events_are_stored_only_when_wider_than_alarm_on():
    hierarchy = _AlertEventHierarchy({"alert-1": "prsAlert", "tag-1": "prsTag"})
    svc = _make_service(hierarchy)
    mes = {
        "parentId": "tag-parent",
        "attributes": {"prsMethodAddress": "sum", "prsEntityTypeCode": 0},
        "initiatedBy": ["alert-1", "tag-1"],
    }

    asyncio.run(MethodsModelCRUD._further_create(svc, mes, "method-1"))

    assert _link_attrs(hierarchy, "alert-1") == [{"cn": ["alert-1"]}]
    assert _link_attrs(hierarchy, "tag-1") == [{"cn": ["tag-1"]}]
    assert all("prsJsonConfigString" not in attrs for _, attrs in hierarchy.added)

    hierarchy.added.clear()
    mes["alertEvents"] = {"alert-1": ["alarm_off", "alarm_on"]}
    asyncio.run(MethodsModelCRUD._further_create(svc, mes, "method-1"))
    assert _link_attrs(hierarchy, "alert-1") == [{
        "cn": ["alert-1"],
        "prsJsonConfigString": {"events": ["alarm_on", "alarm_off"]},
    }]

    hierarchy.added.clear()
    mes["alertEvents"] = {"alert-1": ["alarm_on"]}
    asyncio.run(MethodsModelCRUD._further_create(svc, mes, "method-1"))
    assert _link_attrs(hierarchy, "alert-1") == [{"cn": ["alert-1"]}]


def test_alert_events_reject_empty_unknown_foreign_and_non_alert():
    hierarchy = _AlertEventHierarchy({
        "alert-1": "prsAlert",
        "tag-1": "prsTag",
    })
    svc = _make_service(hierarchy)
    base = {
        "parentId": "tag-parent",
        "attributes": {"prsMethodAddress": "sum", "prsEntityTypeCode": 0},
        "initiatedBy": ["alert-1", "tag-1"],
    }

    empty = {**base, "alertEvents": {"alert-1": []}}
    rejected = asyncio.run(MethodsModelCRUD._further_create(svc, empty, "method-1"))
    assert rejected["error"]["code"] == 422
    assert hierarchy.added == []
    prepared = asyncio.run(MethodsModelCRUD._prepare_method_write(svc, empty, creating=True))
    assert prepared["error"]["code"] == 422

    unknown = {**base, "alertEvents": {"alert-1": ["alarm_fired"]}}
    assert asyncio.run(
        MethodsModelCRUD._prepare_method_write(svc, unknown, creating=True)
    )["error"]["code"] == 422

    foreign = {**base, "alertEvents": {"other-alert": ["alarm_off"]}}
    assert asyncio.run(
        MethodsModelCRUD._prepare_method_write(svc, foreign, creating=True)
    )["error"]["code"] == 422

    tag = {**base, "alertEvents": {"tag-1": ["alarm_off"]}}
    assert asyncio.run(
        MethodsModelCRUD._prepare_method_write(svc, tag, creating=True)
    )["error"]["code"] == 422

    # objectClass[0] был бы top, структурный класс — prsAlert.
    accepted = {**base, "alertEvents": {"alert-1": ["alarm_acked"]}}
    assert asyncio.run(
        MethodsModelCRUD._prepare_method_write(svc, accepted, creating=True)
    ) is None


def test_further_read_returns_alert_events_only_where_stored():
    class Hierarchy:
        async def get_node_class(self, node_id):
            return "prsMethod"

        async def get_node_dn(self, node_id):
            return "cn=method-1,cn=prs"

        async def get_parent(self, node_id):
            raise RuntimeError(node_id)

        async def search(self, payload):
            base = payload.get("base") or ""
            if base.startswith("cn=initiatedBy,"):
                assert "prsJsonConfigString" in payload["attributes"]
                return [
                    ("link-tag", None, {"cn": ["tag-1"]}),
                    (
                        "link-alert",
                        None,
                        {
                            "cn": ["alert-1"],
                            "prsJsonConfigString": ['{"events": ["alarm_acked", "alarm_on"]}'],
                        },
                    ),
                    ("link-plain", None, {"cn": ["alert-2"]}),
                ]
            if base.startswith("cn=parameters,"):
                return []
            raise AssertionError(payload)

    svc = _make_service(Hierarchy())
    result = asyncio.run(MethodsModelCRUD._further_read(svc, {}, {
        "data": [{"id": "method-1", "attributes": {"objectClass": ["prsMethod"]}}]
    }))
    item = result["data"][0]
    assert item["initiatedBy"] == ["tag-1", "alert-1", "alert-2"]
    assert item["alertEvents"] == {"alert-1": ["alarm_on", "alarm_acked"]}
