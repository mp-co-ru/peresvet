"""Каталог методов: проверки привязок, арифметика stdlib и лицензия пакета."""
import importlib.util
from pathlib import Path

from src.services.methods.method_catalog import (
    catalog_call_error,
    numeric_compatible,
    numeric_of,
    validate_binding,
    validate_method_message,
)
from src.services.methods.model_crud.method_package_loader import license_allows


def test_catalog_definition_rejects_initiators_and_non_zero_type():
    rejected = validate_method_message(
        {
            "attributes": {"cn": "add", "prsMethodAddress": "prs.stdlib.add", "prsEntityTypeCode": 1},
            "initiatedBy": ["tag-1"],
        },
        placement="catalog",
        catalog_id=None,
        catalog_address=None,
        require_address=True,
    )
    assert rejected["error"]["code"] == 422
    assert "инициатор" in rejected["error"]["message"]

    ok = validate_method_message(
        {
            "attributes": {"cn": "add", "prsMethodAddress": "prs.stdlib.add"},
            "parameters": [
                {"attributes": {"cn": "a", "prsIndex": 1, "prsValueTypeCode": 2}},
                {"attributes": {"cn": "b", "prsIndex": 2, "prsValueTypeCode": 2}},
            ],
        },
        placement="catalog",
        catalog_id=None,
        catalog_address=None,
        require_address=True,
    )
    assert ok is None


def test_catalog_instance_bindings_and_legacy_untouched():
    query = validate_method_message(
        {
            "catalogMethodId": "cat-1",
            "attributes": {"cn": "sum"},
            "parameters": [
                {"attributes": {"prsIndex": 1, "prsJsonConfigString": {"routingKey": "prsTag.app_api_client.data_get.*", "message": {"tagId": "t"}}}}
            ],
        },
        placement="instance",
        catalog_id="cat-1",
        catalog_address="prs.stdlib.add",
    )
    assert query is None

    ok = validate_method_message(
        {
            "catalogMethodId": "cat-1",
            "attributes": {"cn": "sum", "prsEntityTypeCode": 0},
            "parameters": [
                {"attributes": {"prsIndex": 1, "prsJsonConfigString": {"binding": "tag", "tagId": "t1"}}},
                {"attributes": {"prsIndex": 2, "prsJsonConfigString": {"binding": "literal", "value": 1, "valueTypeCode": 2}}},
                {"attributes": {"prsIndex": 3, "prsJsonConfigString": {"binding": "constant", "constantId": "c1"}}},
            ],
        },
        placement="instance",
        catalog_id="cat-1",
        catalog_address="prs.stdlib.add",
    )
    assert ok is None
    legacy = validate_method_message(
        {
            "attributes": {"cn": "local", "prsMethodAddress": "sum"},
            "parameters": [{"attributes": {"prsJsonConfigString": {"tagId": "t1", "routingKey": "rk"}}}],
        },
        placement="instance",
        catalog_id=None,
        catalog_address=None,
    )
    assert legacy is None
    assert validate_binding({"binding": "tag"}) is not None


def test_catalog_call_checks_arity_and_numeric_types():
    catalog = [
        {"index": 1, "valueTypeCode": 2, "cn": "a"},
        {"index": 2, "valueTypeCode": 2, "cn": "b"},
    ]
    assert catalog_call_error(catalog, [{"index": 1, "data": 1}]) is not None
    assert catalog_call_error(catalog, [{"index": 1, "data": None}, {"index": 2, "data": 1}]) is not None
    assert catalog_call_error(catalog, [{"index": 1, "data": 1}, {"index": 2, "data": 2.5}]) is None
    envelope = {"data": [{"data": [[10, 3, 0]]}]}
    assert numeric_of(envelope) == 3
    assert numeric_compatible(1, 2.5) is False
    assert numeric_compatible(1, 2) is True
    assert numeric_compatible(4, "json") is True


def _stdlib():
    path = Path(__file__).resolve().parents[2] / "methods" / "packages" / "stdlib" / "worker.py"
    spec = importlib.util.spec_from_file_location("peresvet_stdlib_worker", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stdlib_arithmetic_rejects_null_and_division_by_zero():
    worker = _stdlib()
    assert worker._apply(2, 3, lambda x, y: x + y) == 5
    assert worker._apply(5, 2, lambda x, y: x - y) == 3
    assert worker._apply(4, 2.5, lambda x, y: x * y) == 10
    envelope = {"data": [{"data": [[0, 8, 0]]}]}
    assert worker._apply(envelope, 2, lambda x, y: x / y, divide=True) == 4
    assert worker._apply(None, 1, lambda x, y: x + y)["error"]
    assert worker._apply("нет", 1, lambda x, y: x + y)["error"]
    assert worker._apply(1, 0, lambda x, y: x / y, divide=True) == {"error": "деление на ноль"}


def test_package_license_modes(monkeypatch):
    assert license_allows({"license": {"mode": "none"}}) is True
    assert license_allows({"license": {"mode": "env", "env": "PERESVET_METHOD_LICENSE_DEMO"}}) is False
    monkeypatch.setenv("PERESVET_METHOD_LICENSE_DEMO", "token")
    assert license_allows({"license": {"mode": "env", "variable": "PERESVET_METHOD_LICENSE_DEMO"}}) is True
    assert license_allows({"license": {"mode": "server"}}) is False
