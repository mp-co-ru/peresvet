import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.services.connectors.app.connectors_app_svc import ConnectorsApp


class _Logger:
    def info(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass

    def debug(self, *a, **k):
        pass


def test_get_connector_tag_data_and_deleted():
    svc = object.__new__(ConnectorsApp)
    svc._config = SimpleNamespace(svc_name="connectors_app")
    svc._logger = _Logger()
    svc.linked_connectors = {}

    async def search(payload):
        if payload.get("id") == "missing":
            return []
        if payload.get("id") == "c1":
            return [
                (
                    "c1",
                    None,
                    {
                        "prsActive": ["TRUE"],
                        "prsJsonConfigString": [json.dumps({"broker": "mqtt"})],
                    },
                )
            ]
        if payload.get("filter", {}).get("objectClass") == ["prsConnectorTagData"]:
            return [
                ("link", None, {"cn": ["tag-1"], "prsJsonConfigString": [json.dumps({"source": {}})]})
            ]
        if payload.get("id") == "tag-1":
            return [("tag-1", None, {"prsActive": ["TRUE"], "prsValueTypeCode": ["1"]})]
        return []

    svc._hierarchy = SimpleNamespace(search=search)
    empty = asyncio.run(svc.get_connector_tag_data("missing"))
    assert empty == {}
    data = asyncio.run(svc.get_connector_tag_data("c1"))
    assert data["connector"]["prsActive"] is True
    assert data["tags"][0]["tagId"] == "tag-1"
    assert data["tags"][0]["attributes"]["prsValueTypeCode"] == 1

    closed = []

    class WS:
        async def close(self):
            closed.append(True)

    svc.linked_connectors["c1"] = WS()
    asyncio.run(svc._deleted({"id": "c1"}))
    assert closed == [True]
    asyncio.run(svc._deleted({"id": "other"}))
