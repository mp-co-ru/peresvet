import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.services.dataStorages.app.dataStorages_app_base import DataStoragesAppBase


class _App(DataStoragesAppBase):
    async def _create_store_name_for_new_tag(self, ds_id, tag_id):
        return {}

    async def _create_store_for_tag(self, tag_id, ds_id, store):
        pass

    async def _create_store_name_for_new_alert(self, ds_id, alert_id):
        return {}

    async def _create_store_for_alert(self, alert_id, ds_id, store):
        pass

    async def _read_data(self, tag_id, start, finish, order, count, one_before, one_after, value=None):
        return []

    async def _write_tag_data_to_db(self, tag_id):
        pass


class _Logger:
    def debug(self, *a, **k):
        pass

    def info(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


class _Queue:
    async def bind(self, exchange, routing_key):
        return None

    async def unbind(self, exchange, routing_key):
        return None


class _Json:
    def __init__(self, store):
        self.store = store

    async def get(self, name, *a, **k):
        return self.store.get(name)

    async def set(self, name, path="$", obj=None, **k):
        self.store[name] = obj

    async def delete(self, name):
        self.store.pop(name, None)


class _Redis:
    def __init__(self, store):
        self.store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def json(self):
        return _Json(self.store)


class _Catalog:
    def __init__(self):
        self.config = None

    async def search(self, payload):
        if not payload.get("id"):
            return []
        return [(
            "ds-1",
            None,
            {
                "prsEntityTypeCode": ["0"],
                "prsJsonConfigString": [self.config],
                "prsActive": ["TRUE"],
            },
        )]

    async def get_node_id(self, dn):
        return "root"

    async def get_parent(self, node_id):
        return "root", None


def _svc(catalog):
    svc = object.__new__(_App)
    svc._config = SimpleNamespace(svc_name="dataStorages_app_postgresql", datastorage_type=0)
    svc._logger = _Logger()
    svc._hierarchy = catalog
    svc._cache = SimpleNamespace(get_redis=lambda: _Redis({}))
    svc._amqp_consume_queue = _Queue()
    svc._exchange = "ex"
    svc._connection_pools = {}
    svc._ds_connect_tasks = {}
    svc._watched_ds = set()
    svc._create_connection_pool = AsyncMock(return_value="pool")
    return svc


def test_empty_storage_does_not_block_and_connects_after_config():
    catalog = _Catalog()
    svc = _svc(catalog)

    async def run():
        await svc._add_supported_ds("ds-1")
        await asyncio.sleep(0)
        assert svc._create_connection_pool.await_count == 0
        assert "ds-1" not in svc._connection_pools
        assert "ds-1" in svc._watched_ds
        catalog.config = {"dsn": "postgresql://db/prs"}
        await svc.updated({"id": "ds-1"})
        await asyncio.sleep(0)
        assert svc._connection_pools["ds-1"] == "pool"
        await svc.deleted({"id": "ds-1"})
        assert "ds-1" not in svc._connection_pools
        assert "ds-1" not in svc._watched_ds

    asyncio.run(run())


def test_tag_link_is_cached_after_the_pool_is_ready():
    class Catalog(_Catalog):
        async def search(self, payload):
            ids = payload.get("id")
            if ids:
                if "tag-1" in ids:
                    return [(
                        "tag-1",
                        None,
                        {
                            "prsActive": ["TRUE"],
                            "prsUpdate": ["FALSE"],
                            "prsValueTypeCode": ["1"],
                            "prsMaxLineDev": ["0"],
                            "prsStep": ["FALSE"],
                        },
                    )]
                return await super().search(payload)
            if payload.get("base") == "ds-1":
                filt = payload.get("filter") or {}
                if filt.get("objectClass") == ["prsDatastorageTagData"]:
                    return [(
                        "link-1",
                        None,
                        {
                            "cn": ["tag-1"],
                            "prsStore": ['{"table": "t_tag-1"}'],
                        },
                    )]
            return []

    catalog = Catalog()
    catalog.config = {"dsn": "postgresql://db/prs"}
    svc = _svc(catalog)
    store = {}
    svc._cache = SimpleNamespace(get_redis=lambda: _Redis(store))

    async def run():
        await svc._add_supported_ds("ds-1")
        await asyncio.sleep(0)
        cache = store["tag-1.dataStorages_app_postgresql"]
        assert cache["dss"]["ds-1"] == {"table": "t_tag-1"}

    asyncio.run(run())


def test_delete_stops_reconnect_attempts():
    catalog = _Catalog()
    catalog.config = {"dsn": "postgresql://db/prs"}
    svc = _svc(catalog)
    svc._create_connection_pool = AsyncMock(side_effect=RuntimeError("down"))

    async def run():
        await svc._add_supported_ds("ds-1")
        await asyncio.sleep(0)
        assert svc._create_connection_pool.await_count == 1
        await svc.deleted({"id": "ds-1"})
        await asyncio.sleep(0)
        frozen = svc._create_connection_pool.await_count
        await asyncio.sleep(0.05)
        assert svc._create_connection_pool.await_count == frozen
        assert svc._ds_connect_tasks.get("ds-1") is None

    asyncio.run(run())
