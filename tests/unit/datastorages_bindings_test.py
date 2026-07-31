import asyncio
import types

from src.services.dataStorages.app.dataStorages_app_base import DataStoragesAppBase


class _DataStoragesAppForTest(DataStoragesAppBase):
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
    def debug(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


class _Queue:
    def __init__(self):
        self.calls = []

    async def bind(self, exchange, routing_key):
        self.calls.append(("bind", exchange, routing_key))

    async def unbind(self, exchange, routing_key):
        self.calls.append(("unbind", exchange, routing_key))


class _Pool:
    async def close(self):
        pass


class _RedisJson:
    def __init__(self, store):
        self.store = store

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, key):
        self.store.pop(key, None)


class _Redis:
    def __init__(self, store):
        self.store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def json(self):
        return _RedisJson(self.store)


class _Cache:
    def __init__(self):
        self.store = {
            "ds-1.dataStorages_app": {
                "tags": ["tag-1"],
                "alerts": ["alert-1"],
            }
        }

    def get_redis(self):
        return _Redis(self.store)


class _Hierarchy:
    def __init__(self, *, linked_elsewhere):
        self.linked_elsewhere = linked_elsewhere

    async def get_node_id(self, dn):
        assert dn == "cn=dataStorages,cn=prs"
        return "dataStorages-root"

    async def search(self, payload):
        object_class = payload["filter"]["objectClass"][0]
        cn = payload["filter"]["cn"][0]
        if object_class == "prsDatastorageTagData" and cn == "tag-1":
            return self._links("tag-link")
        if object_class == "prsDatastorageAlertData" and cn == "alert-1":
            return self._links("alert-link")
        return []

    def _links(self, prefix):
        links = [(f"{prefix}-current", None, {"cn": [prefix]})]
        if self.linked_elsewhere:
            links.append((f"{prefix}-other", None, {"cn": [prefix]}))
        return links

    async def get_parent(self, node_id):
        if node_id.endswith("-current"):
            return "ds-1", None
        return "ds-2", None


def _make_service(*, linked_elsewhere):
    svc = object.__new__(_DataStoragesAppForTest)
    svc._hierarchy = _Hierarchy(linked_elsewhere=linked_elsewhere)
    svc._cache = _Cache()
    svc._amqp_consume_queue = _Queue()
    svc._exchange = "main"
    svc._config = types.SimpleNamespace(svc_name="dataStorages_app")
    svc._logger = _Logger()
    svc._connection_pools = {"ds-1": _Pool()}
    return svc


def test_remove_supported_ds_keeps_entity_bindings_when_other_ds_links_exist():
    svc = _make_service(linked_elsewhere=True)

    asyncio.run(DataStoragesAppBase._remove_supported_ds(svc, "ds-1"))

    routing_keys = [call[2] for call in svc._amqp_consume_queue.calls]
    assert "prsTag.app.data_get.tag-1" not in routing_keys
    assert "prsTag.app.data_set.tag-1" not in routing_keys
    assert "prsAlert.app.alarm_on.alert-1" not in routing_keys
    assert "ds-1" not in svc._connection_pools
    assert "ds-1.dataStorages_app" not in svc._cache.store


def test_remove_supported_ds_unbinds_entities_without_other_ds_links():
    svc = _make_service(linked_elsewhere=False)

    asyncio.run(DataStoragesAppBase._remove_supported_ds(svc, "ds-1"))

    routing_keys = [call[2] for call in svc._amqp_consume_queue.calls]
    assert "prsTag.app.data_get.tag-1" in routing_keys
    assert "prsTag.app.data_set.tag-1" in routing_keys
    assert "prsAlert.app.alarm_on.alert-1" in routing_keys
