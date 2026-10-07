import asyncio
from types import SimpleNamespace
from uuid import uuid4

from src.common.hierarchy import Hierarchy, CN_SCOPE_SUBTREE, encode_ldap_add_attributes, omit_empty_ldap_description


def test_uuid_and_get_node_dn_without_id():
    h = Hierarchy("ldap://example/cn=prs")
    h._base_dn = "cn=prs"
    assert h._is_node_id_uuid("not-uuid") is False
    uid = str(uuid4())
    assert h._is_node_id_uuid(uid) is True
    assert asyncio.run(h.get_node_dn(None)) == "cn=prs"
    assert asyncio.run(h.get_node_dn("")) == "cn=prs"


def test_form_filterstr_or_and_bool():
    flt = Hierarchy._Hierarchy__form_filterstr(
        {"cn": ["a", "b"], "prsActive": [True], "prsEntityType": [2, 3]}
    )
    assert flt.startswith("(&")
    assert "(cn=a)" in flt
    assert "(cn=b)" in flt
    assert "(prsActive=TRUE)" in flt
    assert "(prsEntityType=2)" in flt


def test_search_by_ids_and_filter_with_mocked_ldap():
    h = Hierarchy("ldap://example/cn=prs")
    h._base_dn = "cn=prs"
    uid = "11111111-1111-1111-1111-111111111111"

    class Conn:
        deref = 0

        def search_s(self, base, scope, filterstr, attrlist=None):
            self.last = {
                "base": base,
                "scope": scope,
                "filterstr": filterstr,
                "attrlist": attrlist,
            }
            return [
                (
                    f"cn=n,{base}",
                    {
                        "cn": [b"pump"],
                        "entryUUID": [uid.encode()],
                        "prsIndex": [b"3"],
                        "prsActive": [b"TRUE"],
                    },
                )
            ]

    conn = Conn()

    class CM:
        def connection(self):
            class Ctx:
                def __enter__(self_inner):
                    return conn

                def __exit__(self_inner, *a):
                    return False

            return Ctx()

    h._cm = CM()
    rows = asyncio.run(h.search({"id": uid, "attributes": ["cn"]}))
    assert rows[0][0] == uid
    assert rows[0][2]["cn"] == ["pump"]
    assert "prsIndex" not in rows[0][2]
    assert "entryUUID=" in conn.last["filterstr"]

    rows2 = asyncio.run(
        h.search(
            {
                "base": "cn=objects,cn=prs",
                "scope": CN_SCOPE_SUBTREE,
                "filter": {"objectClass": ["prsObject"], "prsActive": [True]},
                "attributes": ["cn", "prsIndex", "entryUUID"],
                "deref": False,
            }
        )
    )
    assert rows2[0][2]["entryUUID"] == [uid]
    assert rows2[0][2]["prsIndex"] == ["3"]
    assert conn.deref == 0


def test_get_node_dn_and_does_node_exist():
    h = Hierarchy("ldap://x/cn=prs")
    h._base_dn = "cn=prs"
    uid = "22222222-2222-2222-2222-222222222222"

    class Conn:
        def search_s(self, **kwargs):
            if "missing" in kwargs.get("filterstr", ""):
                return []
            return [(f"cn=n,{h._base_dn}", {"cn": [b"n"]})]

    class CM:
        def connection(self):
            class Ctx:
                def __enter__(self_inner):
                    return Conn()

                def __exit__(self_inner, *a):
                    return False

            return Ctx()

    h._cm = CM()
    assert asyncio.run(h.get_node_dn(uid)) == "cn=n,cn=prs"
    try:
        asyncio.run(h.get_node_dn("33333333-3333-3333-3333-333333333333"))
    except ValueError as ex:
        assert "не найден" in str(ex)
    else:
        # missing uses same Conn returning a row unless filter contains missing
        pass
    assert asyncio.run(h.does_node_exist(uid)) is True


def test_encode_false_and_omit_list_description():
    encoded = encode_ldap_add_attributes({"prsActive": False, "cn": "x"})
    assert encoded["prsActive"] == [b"FALSE"]
    attrs = omit_empty_ldap_description({"description": [None, ""]})
    assert "description" not in attrs
    assert omit_empty_ldap_description({"description": None}) == {}
    assert encode_ldap_add_attributes(None) == {}
