import json

from src.common.hierarchy import encode_ldap_add_attributes, omit_empty_ldap_description


def test_encode_ldap_add_omits_empty_description():
    encoded = encode_ldap_add_attributes(
        {
            "cn": "speed",
            "description": "",
            "prsIndex": 1,
            "prsJsonConfigString": {"source": "tag"},
            "objectClass": ["prsMethodParameter"],
        }
    )

    assert b"speed" in encoded["cn"]
    assert "description" not in encoded
    assert encoded["prsIndex"] == [b"1"]
    assert json.loads(encoded["prsJsonConfigString"][0].decode()) == {"source": "tag"}
    assert encoded["objectClass"] == [b"prsMethodParameter"]


def test_encode_ldap_add_omits_none_and_empty_list_values():
    encoded = encode_ldap_add_attributes(
        {
            "cn": ["speed"],
            "description": [""],
            "note": None,
            "prsActive": True,
        }
    )

    assert "description" not in encoded
    assert "note" not in encoded
    assert encoded["prsActive"] == [b"TRUE"]
    assert encoded["cn"] == [b"speed"]


def test_encode_ldap_add_keeps_space_placeholder_and_text():
    encoded = encode_ldap_add_attributes(
        {
            "prsMethodAddress": " ",
            "description": "Средняя скорость",
        }
    )

    assert encoded["prsMethodAddress"] == [b" "]
    assert encoded["description"] == ["Средняя скорость".encode("utf-8")]


def test_omit_empty_ldap_description_from_method_parameter_payload():
    attrs = omit_empty_ldap_description(
        {
            "cn": "speed",
            "description": "",
            "prsIndex": "1",
            "prsJsonConfigString": {"source": "tag"},
        }
    )
    assert "description" not in attrs
    assert attrs["cn"] == "speed"

    kept = omit_empty_ldap_description({"cn": "speed", "description": "источник скорости"})
    assert kept["description"] == "источник скорости"
