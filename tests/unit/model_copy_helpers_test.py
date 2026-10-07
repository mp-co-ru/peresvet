import asyncio
from types import SimpleNamespace
from uuid import uuid4

from src.common.model_copy import (
    _ldap_row_to_flat_payload,
    _list_data_storage_node_ids,
    _remap_link_operations,
    _safe_json_ldap,
    collect_subtree_nodes,
    copy_single_method,
    copy_subtree_rooted_at,
    ensure_attrs_for_create,
    filter_plain_attrs_for_class,
    first_ldap_attr_value,
    ldap_attrs_to_plain,
    order_nodes_tree_parents_first_async,
    pending_internal_refs,
    remap_initiated_by,
    remap_uuids_in_structure,
    uniquify_cn_under_parent,
)

OLD = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
NEW = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
EXT = "cccccccc-cccc-cccc-cccc-cccccccccccc"
ROOT = "11111111-1111-1111-1111-111111111111"
CHILD = "22222222-2222-2222-2222-222222222222"


def test_attr_helpers_and_remap():
    raw = {
        "CN": ["pump"],
            "prsMethodAddress": [b"/methods/m"],
        "prsActive": ["TRUE"],
        "prsJsonConfigString": ['{"tag": "%s"}' % OLD],
        "objectClass": ["prsTag"],
        "entryUUID": [OLD],
        "empty": [None],
        "multi": ["a", "b"],
    }
    assert first_ldap_attr_value(raw, "cn") == "pump"
    assert first_ldap_attr_value(raw, "prsMethodAddress") == "/methods/m"
    assert first_ldap_attr_value({"x": "z"}, "x") == "z"
    assert first_ldap_attr_value({}, "cn") is None
    plain = ldap_attrs_to_plain(raw)
    assert plain["prsActive"] is True
    assert plain["prsJsonConfigString"]["tag"] == OLD
    assert "objectClass" not in plain
    filtered = filter_plain_attrs_for_class({**plain, "unknown": 1}, "prsTag")
    assert "unknown" not in filtered
    attrs = {}
    ensure_attrs_for_create("prsMethod", {"cn": ["m"], "prsMethodAddress": []}, attrs)
    assert attrs["cn"] == "m"
    assert attrs["prsMethodAddress"] == " "
    mapped = remap_uuids_in_structure(
        {"ref": OLD, "text": f"id={OLD}", "keep": EXT, "n": 1},
        {OLD: NEW},
        frozenset({OLD}),
    )
    assert mapped["ref"] == NEW
    assert NEW in mapped["text"]
    assert mapped["keep"] == EXT
    assert remap_initiated_by(None, {}, frozenset()) == []
    assert remap_initiated_by([OLD, EXT], {OLD: NEW}, frozenset({OLD})) == [NEW, EXT]
    assert pending_internal_refs({"x": OLD}, frozenset({OLD}), {}) is True
    assert pending_internal_refs({"x": OLD}, frozenset({OLD}), {OLD: NEW}) is False
    assert _safe_json_ldap(None, {}) == {}
    assert _safe_json_ldap(["{}"], {}) == {}
    assert _safe_json_ldap(["not json"], {}) == "not json"
    assert _safe_json_ldap([{"a": 1}], {}) == {"a": 1}
    flat = _ldap_row_to_flat_payload(
        {
            "entryUUID": [OLD],
            "prsActive": ["FALSE"],
            "prsEntityTypeCode": ["2"],
            "prsJsonConfigString": ['{"q":1}'],
            "cn": ["t"],
        }
    )
    assert "entryUUID" not in flat
    assert flat["prsActive"] is False
    assert flat["prsEntityTypeCode"] == 2
    ops = _remap_link_operations(
        [
            {
                "attributes": {"prsJsonConfigString": {"tagId": OLD}},
                "parameters": [{"attributes": {"prsJsonConfigString": {"id": OLD}}}],
            }
        ],
        {OLD: NEW},
        frozenset({OLD}),
    )
    assert ops[0]["attributes"]["prsJsonConfigString"]["tagId"] == NEW


def test_uniquify_cn_and_order_and_collect():
    class H:
        def __init__(self):
            self.calls = 0

        async def search(self, payload):
            self.calls += 1
            if payload.get("filter", {}).get("objectClass") == [
                "prsObject",
                "prsTag",
                "prsAlert",
                "prsMethod",
            ]:
                return [(ROOT, None, {"cn": ["root"]}), (CHILD, None, {"cn": ["child"]})]
            if self.calls == 1:
                return [("exists", None, {})]
            return []

        async def get_node_class(self, nid):
            return "prsObject" if nid == ROOT else "prsTag"

        async def get_parent(self, nid):
            if nid == CHILD:
                return ROOT, None
            return "outside", None

        async def get_node_id(self, dn):
            return "ds-root"

    h = H()
    attrs = {"cn": "pump"}
    asyncio.run(uniquify_cn_under_parent(h, ROOT, attrs))
    assert attrs["cn"] == "pump (копия)"
    nodes = asyncio.run(collect_subtree_nodes(h, ROOT))
    assert {n[0] for n in nodes} == {ROOT, CHILD}
    ordered = asyncio.run(order_nodes_tree_parents_first_async(h, ROOT, nodes))
    assert ordered[0][0] == ROOT
    assert ordered[1][0] == CHILD


def test_list_ds_ids_and_copy_object_tree():
    class H:
        async def get_node_id(self, dn):
            return "ds-root"

        async def get_node_class(self, nid):
            return {ROOT: "prsObject", CHILD: "prsTag"}[nid]

        async def get_parent(self, nid):
            if nid == ROOT:
                return "parent", None
            return ROOT, None

        async def get_node_dn(self, nid):
            return f"cn={nid},cn=prs"

        async def search(self, payload):
            if payload.get("base") == "ds-root":
                return [("ds1", None, {"cn": ["ds"]})]
            if payload.get("filter", {}).get("objectClass") == [
                "prsObject",
                "prsTag",
                "prsAlert",
                "prsMethod",
            ]:
                return [
                    (ROOT, None, {"cn": ["obj"], "prsActive": ["TRUE"]}),
                    (CHILD, None, {"cn": ["tag"], "prsActive": ["TRUE"], "prsValueTypeCode": ["1"]}),
                ]
            if "initiatedBy" in str(payload.get("base", "")):
                return []
            if "parameters" in str(payload.get("base", "")):
                return []
            if payload.get("filter", {}).get("cn"):
                return []
            return []

    created = []

    async def post_message(*, mes, reply, routing_key):
        created.append((routing_key, mes["attributes"]["cn"]))
        return {"id": f"new-{mes['attributes']['cn']}"}

    ids = asyncio.run(_list_data_storage_node_ids(H()))
    assert ids == ["ds1"]
    result = asyncio.run(
        copy_subtree_rooted_at(
            H(),
            post_message,
            root_source_id=ROOT,
            expected_root_class="prsObject",
            new_parent_id="new-parent",
            new_root_cn="obj-copy",
        )
    )
    assert result["id"] == "new-obj-copy"
    assert created[0][0] == "prsObject.api_crud.create"
    assert created[1][0] == "prsTag.api_crud.create"


def test_copy_single_method_and_wrong_class():
    class H:
        async def get_node_class(self, nid):
            return "prsTag" if nid == "not-method" else "prsMethod"

        async def get_node_dn(self, nid):
            return f"cn={nid}"

        async def search(self, payload):
            if payload.get("id") == ["m1"]:
                return [("m1", None, {"cn": ["m"], "prsMethodAddress": [" "]})]
            return []

    async def post_message(**kwargs):
        return {"id": "copied"}

    bad = asyncio.run(
        copy_single_method(H(), post_message, source_id="not-method", new_parent_id="p", subtree_ids=frozenset(), id_map={})
    )
    assert bad["error"]["code"] == 422
    ok = asyncio.run(
        copy_single_method(H(), post_message, source_id="m1", new_parent_id="p", subtree_ids=frozenset(), id_map={})
    )
    assert ok == {"id": "copied"}


def test_copy_subtree_wrong_class():
    class H:
        async def get_node_class(self, nid):
            return "prsTag"

    async def post_message(**kwargs):
        return {}

    res = asyncio.run(
        copy_subtree_rooted_at(
            H(), post_message, root_source_id=ROOT, expected_root_class="prsObject", new_parent_id="p"
        )
    )
    assert res["error"]["code"] == 422
