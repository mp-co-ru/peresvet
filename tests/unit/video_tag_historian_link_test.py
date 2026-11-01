import asyncio
import types

from src.services.dataStorages.app.postgresql.dataStorages_app_postgresql_svc import (
    DataStoragesAppPostgreSQL,
)
from src.services.dataStorages.model_crud.dataStorages_model_crud_svc import DataStoragesModelCRUD
from src.services.dataStorages.model_crud.dataStorages_model_crud_v2_svc import DataStoragesModelCRUDV2


def _crud_dummy(search, posted, add_calls):
    dummy = types.SimpleNamespace()

    async def _post_message(*_args, **kwargs):
        posted.append(kwargs.get("routing_key"))
        return {"prsStore": {"table": "t_tag"}}

    async def _get_node_dn(_node_id: str):
        return "cn=psql,cn=dataStorages,cn=prs"

    async def _get_node_id(_dn: str):
        return "tags-node"

    async def _add(base, attribute_values):
        add_calls.append((base, attribute_values))
        return "new-link"

    async def _add_alias(*_args, **_kwargs):
        return None

    dummy._post_message = _post_message
    dummy._hierarchy = types.SimpleNamespace(
        search=search,
        get_node_dn=_get_node_dn,
        get_node_id=_get_node_id,
        add=_add,
        add_alias=_add_alias,
    )
    dummy._config = types.SimpleNamespace(
        hierarchy={"class": "prsDataStorage"},
        svc_name="test",
    )
    dummy._logger = types.SimpleNamespace(error=lambda *a, **k: None, info=lambda *a, **k: None)
    dummy._video_storage_link = types.MethodType(DataStoragesModelCRUD._video_storage_link, dummy)
    dummy._tag_is_video_stream = types.MethodType(DataStoragesModelCRUD._tag_is_video_stream, dummy)
    return dummy


def test_video_stream_tag_is_not_linked_to_historian():
    posted = []
    add_calls = []

    async def search(payload):
        attrs = payload.get("attributes") or []
        if payload.get("id") == "ds-psql" and "prsEntityTypeCode" in attrs:
            return [("ds-psql", None, {"prsEntityTypeCode": ["0"], "prsJsonConfigString": ["{}"]})]
        if payload.get("id") == "tag-video" and attrs == ["prsValueTypeCode"]:
            return [("tag-video", None, {"prsValueTypeCode": ["6"]})]
        return []

    dummy = _crud_dummy(search, posted, add_calls)
    asyncio.run(
        DataStoragesModelCRUDV2._link_tag(
            dummy,
            payload={"tagId": "tag-video", "dataStorageId": "ds-psql"},
        )
    )

    assert posted == []
    assert add_calls == []


def test_ordinary_tag_is_still_linked_to_historian():
    posted = []
    add_calls = []

    async def search(payload):
        attrs = payload.get("attributes") or []
        if payload.get("id") == "ds-psql" and "prsEntityTypeCode" in attrs:
            return [("ds-psql", None, {"prsEntityTypeCode": ["0"], "prsJsonConfigString": ["{}"]})]
        if attrs == ["prsValueTypeCode"]:
            return [("tag-1", None, {"prsValueTypeCode": ["1"]})]
        if payload.get("filter", {}).get("objectClass") == ["prsDatastorageTagData"]:
            return []
        return []

    dummy = _crud_dummy(search, posted, add_calls)
    asyncio.run(
        DataStoragesModelCRUD._link_tag(
            dummy,
            payload={"tagId": "tag-1", "dataStorageId": "ds-psql"},
        )
    )

    assert posted
    assert any(call[1].get("cn") == "tag-1" for call in add_calls)


def test_unlink_tag_drops_the_tag_table_and_answers_the_rpc():
    svc = DataStoragesAppPostgreSQL.__new__(DataStoragesAppPostgreSQL)
    seen = []
    dropped = []

    async def search(payload):
        seen.append(payload)
        return [("link", None, {"prsStore": ['{"table": "t_tag-video"}']})]

    class _Conn:
        async def execute(self, sql):
            dropped.append(sql)

    class _Pool:
        def acquire(self):
            return self

        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, *_args):
            return None

    class _Redis:
        def json(self):
            return self

        async def arrindex(self, *_args):
            return -1

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    async def still_linked(_tag_id, _ds_id):
        return True

    svc._hierarchy = types.SimpleNamespace(search=search)
    svc._conf = types.SimpleNamespace(svc_name="test")
    svc._logger = types.SimpleNamespace(error=lambda *a, **k: None, info=lambda *a, **k: None)
    svc._connection_pools = {"ds-psql": _Pool()}
    svc._cache = types.SimpleNamespace(get_redis=lambda: _Redis())
    svc._tag_linked_to_other_datastorage = still_linked

    result = asyncio.run(svc._unlink_tag({"tagId": "tag-video", "dataStorageId": "ds-psql"}))

    assert result == {}
    assert seen[0]["filter"]["objectClass"] == ["prsDatastorageTagData"]
    assert dropped == ['drop table if exists "t_tag-video"']
