from src.mcp_server.payloads import (
    alert_create_payload,
    alarms_query_to_params,
    auth_headers,
    connector_create_payload,
    connector_linked_tag_payload,
    connector_update_payload,
    copy_payload,
    crud_query_to_params,
    extract_created_id,
    linked_tag_payload,
    method_parameter_payload,
    prepare_data_query,
    schedule_create_payload,
)


def test_crud_query_to_params_repeats_ids_and_flags():
    params = dict(
        crud_query_to_params(
            {
                "id": ["a", "b"],
                "base": "root",
                "scope": 2,
                "hierarchy": True,
                "getParent": False,
                "getLinkedTags": True,
                "filter": {"cn": ["pump"]},
            }
        )
    )
    assert params["base"] == "root"
    assert params["scope"] == "2"
    assert params["hierarchy"] == "true"
    assert params["getParent"] == "false"
    assert params["getLinkedTags"] == "true"
    assert '"cn"' in params["filter"]
    ids = [v for k, v in crud_query_to_params({"id": ["a", "b"]}) if k == "id"]
    assert ids == ["a", "b"]


def test_prepare_data_query_maps_all_records_and_blocks_eval_context():
    params = dict(
        prepare_data_query(
            {
                "tagId": "tag-1",
                "allRecordsAsValue": False,
                "calendarTagId": "cal-1",
                "evalContextTagId": "must-not-pass",
            }
        )
    )
    assert params["tagId"] == "tag-1"
    assert params["calendarTagId"] == "cal-1"
    assert "evalContextTagId" not in params
    assert '"allRecordsAsValue": false' in params["params"] or params["params"].endswith("false}")


def test_copy_payload_shapes():
    obj = copy_payload(source_id="src", parent_id="parent", attributes={"cn": "copy"})
    assert obj == {"sourceId": "src", "parentId": "parent", "attributes": {"cn": "copy"}}
    conn = copy_payload(source_id="src", extra={"copyLinkedTags": True})
    assert conn == {"sourceId": "src", "copyLinkedTags": True}


def test_alert_and_schedule_payloads():
    alert = alert_create_payload(parent_id="tag-1", cn="hi", value=42, high=False, auto_ack=False)
    assert alert["parentId"] == "tag-1"
    cfg = alert["attributes"]["prsJsonConfigString"]
    assert cfg == {"value": 42, "high": False, "autoAck": False}
    schedule = schedule_create_payload(
        cn="hourly",
        start="2026-01-01T00:00:00",
        interval_type="minutes",
        interval_value=15,
        end="2026-01-02T00:00:00",
    )
    assert schedule["attributes"]["cn"] == "hourly"
    assert schedule["attributes"]["prsJsonConfigString"]["interval_type"] == "minutes"
    assert schedule["attributes"]["prsJsonConfigString"]["interval_value"] == 15


def test_alarms_query_repeats_parent_ids():
    params = alarms_query_to_params(
        {"parentId": ["o1", "o2"], "getChildren": True, "fired": False, "format": True}
    )
    parent_ids = [v for k, v in params if k == "parentId"]
    assert parent_ids == ["o1", "o2"]
    as_dict = dict(params)
    assert as_dict["getChildren"] == "true"
    assert as_dict["fired"] == "false"
    assert as_dict["format"] == "true"


def test_connector_linked_tag_compact_and_explicit():
    compact = connector_linked_tag_payload(
        {"tagId": "t1", "source": {"topic": "a/b"}, "maxDev": 0.1, "cn": "link"}
    )
    assert compact["tagId"] == "t1"
    assert compact["attributes"]["cn"] == "link"
    assert compact["attributes"]["prsJsonConfigString"]["source"] == {"topic": "a/b"}
    assert compact["attributes"]["prsJsonConfigString"]["maxDev"] == 0.1

    explicit = connector_linked_tag_payload(
        {"tagId": "t2", "attributes": {"prsJsonConfigString": {"source": {}}}}
    )
    assert explicit["attributes"]["prsJsonConfigString"] == {"source": {}}


def test_connector_create_and_update_payloads():
    created = connector_create_payload(
        cn="mqtt",
        config={"broker": "mqtt://rabbitmq"},
        linked_tags=[{"tagId": "t1", "source": {"topic": "x"}}],
    )
    assert created["attributes"]["cn"] == "mqtt"
    assert created["attributes"]["prsJsonConfigString"]["broker"] == "mqtt://rabbitmq"
    assert created["linkedTags"][0]["tagId"] == "t1"

    updated = connector_update_payload(
        connector_id="c1",
        unlink_tags=["t1"],
        linked_tags=[{"tagId": "t2", "config": {"source": {"topic": "y"}}}],
    )
    assert updated["id"] == "c1"
    assert updated["unlinkTags"] == ["t1"]
    assert updated["linkedTags"][0]["attributes"]["prsJsonConfigString"]["source"]["topic"] == "y"


def test_method_parameter_and_integrational_link():
    param = method_parameter_payload({"cn": "start", "config": {"JSONata": "$.start"}, "index": 0})
    assert param["attributes"]["cn"] == "start"
    assert param["attributes"]["prsIndex"] == 0
    assert param["attributes"]["prsJsonConfigString"] == {"JSONata": "$.start"}

    link = linked_tag_payload(
        {
            "tagId": "t1",
            "operations": [
                {
                    "cn": "select",
                    "query": "select 1",
                    "parameters": [{"cn": "start", "config": {"JSONata": "$.start"}}],
                }
            ],
        }
    )
    op = link["operations"][0]
    assert op["attributes"]["cn"] == "select"
    assert op["attributes"]["prsJsonConfigString"]["query"] == "select 1"
    assert op["parameters"][0]["attributes"]["cn"] == "start"


def test_extract_created_id_and_auth_headers():
    assert extract_created_id({"ok": True, "data": {"id": "abc"}}) == "abc"
    assert extract_created_id({"ok": False, "data": {"id": "abc"}}) is None
    assert auth_headers("") == {}
    assert auth_headers("tok") == {"Authorization": "Bearer tok"}
    assert auth_headers("Bearer tok") == {"Authorization": "Bearer tok"}
