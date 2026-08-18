from src.common.api_crud_svc import (
    NodeAttributes,
    coerce_optional_directory_string,
    coerce_prs_json_strings_in_mapping_tree,
)


def test_empty_description_string_becomes_none():
    assert coerce_optional_directory_string("") is None
    assert coerce_optional_directory_string([""]) is None
    assert coerce_optional_directory_string(" ") == " "
    assert coerce_optional_directory_string("скорость") == "скорость"


def test_node_attributes_empty_description_becomes_none():
    attrs = NodeAttributes.model_validate({"cn": "speed", "description": ""})
    assert attrs.description is None


def test_put_payload_tree_coerces_empty_parameter_description():
    payload = {
        "id": "method-1",
        "initiatedBy": ["tag-1"],
        "parameters": [
            {
                "attributes": {
                    "cn": "speed",
                    "description": "",
                    "prsJsonConfigString": {"source": "tag"},
                }
            }
        ],
    }
    coerce_prs_json_strings_in_mapping_tree(payload)
    assert payload["parameters"][0]["attributes"]["description"] is None
    assert payload["parameters"][0]["attributes"]["cn"] == "speed"
