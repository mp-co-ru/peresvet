import asyncio

import pytest

from src.services.methods.app.methods_app_svc import MethodsApp
from src.services.methods.method_description import (
    apply_method_description,
    parse_method_description,
)


DESCRIPTION = """
folders:
  - cn: stdlib
    description: Арифметика
    methods:
      - cn: add
        address: prs.stdlib.add
        parameters:
          - cn: a
            type: float
          - name: b
            index: 2
            prsValueTypeCode: 2
        probe: [2, 3]
    folders:
      - cn: extra
        methods:
          - address: prs.stdlib.echo
            parameters:
              - cn: text
                type: string
methods:
  - cn: bare
    prsMethodAddress: prs.example.bare
"""


def test_parse_method_description_tree_and_default_probe():
    tree = parse_method_description(DESCRIPTION)
    assert tree["folders"][0]["cn"] == "stdlib"
    add = tree["folders"][0]["methods"][0]
    assert add["prsMethodAddress"] == "prs.stdlib.add"
    assert add["parameters"][0] == {
        "cn": "a",
        "prsIndex": 1,
        "prsValueTypeCode": 2,
        "description": "",
    }
    assert add["parameters"][1]["cn"] == "b"
    assert add["parameters"][1]["prsIndex"] == 2
    assert add["probe"] == [2, 3]
    echo = tree["folders"][0]["folders"][0]["methods"][0]
    assert echo["cn"] == "prs.stdlib.echo"
    assert echo["probe"] == ["probe"]
    assert tree["methods"][0]["probe"] == []


def test_parse_method_description_rejects_empty_and_unknown_type():
    with pytest.raises(ValueError, match="пуст"):
        parse_method_description("   ")
    with pytest.raises(ValueError, match="неизвестный тип"):
        parse_method_description(
            "methods:\n  - address: prs.x\n    parameters:\n      - cn: a\n        type: color\n"
        )


def test_apply_method_description_reuses_folder_and_address():
    folders = {}
    methods = {}

    async def ensure_folder(parent_id, folder):
        key = (parent_id, folder["cn"])
        if key in folders:
            return folders[key], "exists", ""
        folders[key] = f"id-{folder['cn']}"
        return folders[key], "created", ""

    async def create_method(parent_id, method):
        methods[method["prsMethodAddress"]] = f"m-{method['cn']}"
        return methods[method["prsMethodAddress"]], "created", ""

    async def find_by_address(address):
        return methods.get(address)

    tree = parse_method_description(DESCRIPTION)
    first = asyncio.run(
        apply_method_description(
            tree,
            "root",
            ensure_folder=ensure_folder,
            create_method=create_method,
            find_by_address=find_by_address,
        )
    )
    assert [item["status"] for item in first["created"] if item["kind"] == "method"] == [
        "created",
        "created",
        "created",
    ]
    assert len(first["probes"]) == 3
    second = asyncio.run(
        apply_method_description(
            tree,
            "root",
            ensure_folder=ensure_folder,
            create_method=create_method,
            find_by_address=find_by_address,
        )
    )
    assert [item["status"] for item in second["created"]] == ["exists"] * 5
    add = next(item for item in second["probes"] if item["address"] == "prs.stdlib.add")
    assert add["arguments"] == [2, 3]


def test_probe_method_reports_call_result_and_timeout():
    svc = object.__new__(MethodsApp)

    class Exchange:
        async def call(self, address, *args):
            assert address == "prs.stdlib.add"
            assert args == (2, 3)
            return 5

    svc._rpc_exchange = Exchange()
    ok = asyncio.run(svc._probe_method({"address": "prs.stdlib.add", "cn": "add", "arguments": [2, 3]}))
    assert ok["ok"] is True
    assert ok["result"] == 5

    class Slow:
        async def call(self, address, *args):
            await asyncio.sleep(1)
            return 1

    svc._rpc_exchange = Slow()
    svc._probe_timeout = 0.05
    failed = asyncio.run(svc._probe_method({"address": "prs.slow", "arguments": []}))
    assert failed["ok"] is False
    assert "не ответил" in failed["error"]

    svc._rpc_exchange = Exchange()
    error = asyncio.run(svc._probe_method({"address": "", "arguments": []}))
    assert error["ok"] is False
