from decimal import Decimal

from src.common.consts import CNTagValueTypes as TVT
from src.common.tag_max_line_dev import (
    filter_data_points_for_storage,
    filter_points_by_max_line_dev,
    parse_prs_max_line_dev_from_ldap_attrs,
    should_discard_data_point,
    should_discard_point_for_max_line_dev,
)


def test_parse_prs_max_line_dev():
    assert parse_prs_max_line_dev_from_ldap_attrs({}) == 0.0
    assert parse_prs_max_line_dev_from_ldap_attrs({"prsMaxLineDev": [None]}) == 0.0
    assert parse_prs_max_line_dev_from_ldap_attrs({"prsMaxLineDev": [""]}) == 0.0
    assert parse_prs_max_line_dev_from_ldap_attrs({"prsMaxLineDev": ["0.5"]}) == 0.5
    assert parse_prs_max_line_dev_from_ldap_attrs({"prsMaxLineDev": [b"1.25"]}) == 1.25
    assert parse_prs_max_line_dev_from_ldap_attrs({"prsMaxLineDev": ["nope"]}) == 0.0


def test_discard_rules_by_type_and_quality():
    assert should_discard_data_point(TVT.CN_DOUBLE, 0.1, 1.0, 0, 1.05, 0) is True
    assert should_discard_data_point(TVT.CN_DOUBLE, 0.1, 1.0, 0, 1.5, 0) is False
    assert should_discard_data_point(TVT.CN_DOUBLE, 0.1, 1.0, 0, 1.05, 100) is False
    assert should_discard_data_point(TVT.CN_TABLE, 1, 1, 0, 1, 0) is False
    assert should_discard_data_point(TVT.CN_STR, 1, "a", 0, "a", 0) is True
    assert should_discard_data_point(TVT.CN_STR, 0, "a", 0, "a", 0) is False
    assert should_discard_data_point(TVT.CN_JSON, 1, {"a": 1}, 0, b'{"a": 1}', 0) is True
    assert should_discard_data_point(TVT.CN_INT, 0, None, None, None, None) is True
    assert should_discard_data_point(99, 1, 1, 0, 2, 0) is False
    assert should_discard_point_for_max_line_dev(TVT.CN_DOUBLE, 0.1, 1.0, 1.05, 0, 0) is True


def test_filter_points_updates_last_accepted():
    points = [(1, 1.0, 0), (2, 1.01, 0), (3, 5.0, 0), "keep"]
    accepted, last_y, last_q = filter_data_points_for_storage(points, TVT.CN_DOUBLE, 0.1, None, None)
    assert accepted[0] == (1, 1.0, 0)
    assert (2, 1.01, 0) not in accepted
    assert accepted[-2] == (3, 5.0, 0)
    assert last_y == 5.0
    acc2, last2 = filter_points_by_max_line_dev([(1,)], TVT.CN_INT, 0, None)
    assert acc2 == [(1,)]
    empty, ly, lq = filter_data_points_for_storage([(1, 1.0, 0), (2, 1.01, 0)], TVT.CN_DOUBLE, 0.5, 1.0, 0)
    assert empty == []
    assert ly == 1.0
    assert should_discard_data_point(TVT.CN_DOUBLE, 1, Decimal("1"), 0, "1.0", 0) is True
