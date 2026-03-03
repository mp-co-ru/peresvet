import asyncio
import datetime
import sys
import types


uvloop_stub = types.ModuleType("uvloop")
uvloop_stub.EventLoopPolicy = asyncio.DefaultEventLoopPolicy
sys.modules.setdefault("uvloop", uvloop_stub)

aio_pika_stub = types.ModuleType("aio_pika")
aio_pika_abc_stub = types.ModuleType("aio_pika.abc")
for _name in (
    "AbstractIncomingMessage",
    "AbstractRobustConnection",
    "AbstractRobustChannel",
    "AbstractRobustExchange",
    "AbstractRobustQueue",
):
    setattr(aio_pika_abc_stub, _name, object)
aio_pika_stub.abc = aio_pika_abc_stub
sys.modules.setdefault("aio_pika", aio_pika_stub)
sys.modules.setdefault("aio_pika.abc", aio_pika_abc_stub)

aiormq_abc_stub = types.ModuleType("aiormq.abc")
aiormq_abc_stub.DeliveredMessage = object
sys.modules.setdefault("aiormq.abc", aiormq_abc_stub)

pamqp_commands_stub = types.ModuleType("pamqp.commands")
pamqp_commands_stub.Basic = object
sys.modules.setdefault("pamqp.commands", pamqp_commands_stub)

redis_stub = types.ModuleType("redis")
redis_asyncio_stub = types.ModuleType("redis.asyncio")
redis_asyncio_stub.Redis = object
redis_asyncio_stub.Pipeline = object


class _BlockingConnectionPool:
    @classmethod
    def from_url(cls, url: str):
        _ = url
        return cls()


redis_asyncio_stub.BlockingConnectionPool = _BlockingConnectionPool
redis_stub.asyncio = redis_asyncio_stub
sys.modules.setdefault("redis", redis_stub)
sys.modules.setdefault("redis.asyncio", redis_asyncio_stub)

pydantic_settings_stub = types.ModuleType("pydantic_settings")
from pydantic import BaseModel as _PydanticBaseModel


class _BaseSettings(_PydanticBaseModel):
    pass


class _PydanticBaseSettingsSource:
    def __init__(self, settings_cls=None):
        self.settings_cls = settings_cls
        self.config = {}


pydantic_settings_stub.BaseSettings = _BaseSettings
pydantic_settings_stub.PydanticBaseSettingsSource = _PydanticBaseSettingsSource
sys.modules.setdefault("pydantic_settings", pydantic_settings_stub)

loguru_stub = types.ModuleType("loguru")


class _LoguruLogger:
    def bind(self, *_args, **_kwargs):
        return self

    def add(self, *_args, **_kwargs):
        return None

    def remove(self, *_args, **_kwargs):
        return None

    def debug(self, *_args, **_kwargs):
        return None

    def info(self, *_args, **_kwargs):
        return None

    def warning(self, *_args, **_kwargs):
        return None

    def error(self, *_args, **_kwargs):
        return None

    def exception(self, *_args, **_kwargs):
        return None


loguru_stub.logger = _LoguruLogger()
sys.modules.setdefault("loguru", loguru_stub)

ldap_stub = types.ModuleType("ldap")
ldap_stub.SCOPE_SUBTREE = 2
ldap_stub.SCOPE_ONELEVEL = 1
ldap_stub.MOD_REPLACE = 2
ldap_stub.MOD_DELETE = 1
ldap_stub.MOD_ADD = 0
sys.modules.setdefault("ldap", ldap_stub)

ldappool_stub = types.ModuleType("ldappool")
ldappool_stub.ConnectionManager = object
sys.modules.setdefault("ldappool", ldappool_stub)

hierarchy_stub = types.ModuleType("src.common.hierarchy")
hierarchy_stub.CN_SCOPE_BASE = 0
hierarchy_stub.CN_SCOPE_ONELEVEL = 1
hierarchy_stub.CN_SCOPE_SUBTREE = 2


class _Hierarchy:
    def __init__(self, *_args, **_kwargs):
        return None


hierarchy_stub.Hierarchy = _Hierarchy
sys.modules.setdefault("src.common.hierarchy", hierarchy_stub)

ds_base_stub = types.ModuleType("src.services.dataStorages.app.dataStorages_app_base")


class _DataStoragesAppBase:
    pass


ds_base_stub.DataStoragesAppBase = _DataStoragesAppBase
sys.modules.setdefault("src.services.dataStorages.app.dataStorages_app_base", ds_base_stub)

ciso_stub = types.ModuleType("ciso8601")


def _parse_datetime(s: str):
    return datetime.datetime.fromisoformat(s)


ciso_stub.parse_datetime = _parse_datetime
sys.modules.setdefault("ciso8601", ciso_stub)

from src.services.dataStorages.app.integrational.dataStorages_app_integrational_base import (
    DataStoragesAppIntegrationalBase,
)
from src.services.dataStorages.app.integrational.dataStorages_app_integrational_utils import OperationKind
from src.services.dataStorages.api_crud.dataStorages_api_crud_v2_router import (
    LinkTagV2,
    read_v2,
    dataStorages_api_crud_app,
)
from src.services.dataStorages.model_crud.dataStorages_model_crud_svc import DataStoragesModelCRUD


def test_link_tag_payload_allows_omitting_attributes_block():
    model = LinkTagV2.model_validate(
        {
            "tagId": "11111111-1111-1111-1111-111111111111",
            "operations": [],
        }
    )
    assert model.tagId == "11111111-1111-1111-1111-111111111111"


def test_v2_read_accepts_normal_query_params_without_q():
    captured: dict = {}

    async def _fake_api_get_read(_request_model, _q, payload):
        captured["payload"] = payload
        return {"data": []}

    class _ErrHandler:
        async def handle_error(self, _res):
            return None

    original = dataStorages_api_crud_app.api_get_read
    dataStorages_api_crud_app.api_get_read = _fake_api_get_read
    try:
        asyncio.run(
            read_v2(
                q=None,
                payload=None,
                id=["2a76d37a-ab6b-1040-82f2-49994dd8ec9e"],
                getLinkedTags=True,
                error_handler=_ErrHandler(),
            )
        )
    finally:
        dataStorages_api_crud_app.api_get_read = original

    payload_obj = captured["payload"]
    assert payload_obj.id == ["2a76d37a-ab6b-1040-82f2-49994dd8ec9e"]
    assert payload_obj.getLinkedTags is True


def test_safe_json_attr_handles_none_without_json_loads_error():
    dummy = types.SimpleNamespace()
    assert DataStoragesModelCRUD._safe_json_attr(dummy, [None], default=None) is None
    assert DataStoragesModelCRUD._safe_json_attr(dummy, [""], default=None) is None
    assert DataStoragesModelCRUD._safe_json_attr(dummy, ['{"a":1}'], default={}) == {"a": 1}
    # Non-JSON string should be returned as-is, not raise.
    assert DataStoragesModelCRUD._safe_json_attr(dummy, ["not-json"], default=None) == "not-json"


def test_further_read_linked_tags_does_not_fail_when_prsstore_is_none():
    dummy = types.SimpleNamespace()
    dummy._safe_json_attr = types.MethodType(DataStoragesModelCRUD._safe_json_attr, dummy)

    async def _search(payload: dict):
        flt = payload.get("filter") or {}
        if flt.get("objectClass") == ["prsDatastorageTagData"]:
            return [
                (
                    "link-1",
                    None,
                    {
                        "cn": ["67ac80aa-ab6b-1040-82f7-49994dd8ec9e"],
                        "prsStore": [None],
                    },
                )
            ]
        return []

    dummy._hierarchy = types.SimpleNamespace(search=_search)

    result = asyncio.run(
        DataStoragesModelCRUD._further_read(
            dummy,
            mes={"getLinkedTags": True, "getLinkedAlerts": False},
            search_result={
                "data": [
                    {
                        "id": "2a76d37a-ab6b-1040-82f2-49994dd8ec9e",
                        "attributes": {"cn": ["abrau_relational"]},
                    }
                ]
            },
        )
    )

    assert len(result["data"]) == 1
    assert len(result["data"][0]["linkedTags"]) == 1
    assert result["data"][0]["linkedTags"][0]["attributes"]["prsStore"] is None


def test_integrational_resolve_operation_cn_reads_child_nodes():
    dummy = types.SimpleNamespace()
    dummy._operation_kind_code = types.MethodType(DataStoragesAppIntegrationalBase._operation_kind_code, dummy)

    async def _search(payload: dict):
        _ = payload
        return [
            ("op-1", None, {"cn": ["get.default"], "prsEntityTypeCode": ["0"]}),
            ("op-2", None, {"cn": ["set.write"], "prsEntityTypeCode": ["1"]}),
        ]

    dummy._hierarchy = types.SimpleNamespace(search=_search)

    op_get = asyncio.run(
        DataStoragesAppIntegrationalBase._resolve_operation_cn_from_link(
            dummy,
            link_id="link-1",
            requested_operation=None,
            expected_kind=OperationKind.GET,
        )
    )
    op_set = asyncio.run(
        DataStoragesAppIntegrationalBase._resolve_operation_cn_from_link(
            dummy,
            link_id="link-1",
            requested_operation="set.write",
            expected_kind=OperationKind.SET,
        )
    )

    assert op_get == "get.default"
    assert op_set == "set.write"


def test_integrational_load_operation_uses_new_cfg_keys_and_param_nodes():
    dummy = types.SimpleNamespace()
    dummy._META_OPERATION_TTL_SEC = 30
    dummy._cache_data = {}
    dummy._safe_json_loads = types.MethodType(DataStoragesAppIntegrationalBase._safe_json_loads, dummy)
    dummy._operation_kind_code = types.MethodType(DataStoragesAppIntegrationalBase._operation_kind_code, dummy)
    dummy._operation_to_cache_payload = types.MethodType(DataStoragesAppIntegrationalBase._operation_to_cache_payload, dummy)
    dummy._meta_cache_key = types.MethodType(DataStoragesAppIntegrationalBase._meta_cache_key, dummy)
    dummy._is_ldap_active = types.MethodType(DataStoragesAppIntegrationalBase._is_ldap_active, dummy)
    dummy._config = types.SimpleNamespace(svc_name="test_integrational")

    async def _meta_cache_get(_self, key: str):
        return _self._cache_data.get(key)

    async def _meta_cache_set(_self, key: str, data: dict, ttl_sec: int):
        _ = ttl_sec
        _self._cache_data[key] = data

    async def _search(payload: dict):
        flt = payload.get("filter") or {}
        obj = (flt.get("objectClass") or [None])[0]
        if obj == "prsDatastorageTagOperation":
            return [
                (
                    "op-node-1",
                    None,
                    {
                        "cn": ["erp.orders.select.v1"],
                        "prsActive": ["TRUE"],
                        "prsEntityTypeCode": ["0"],
                        "prsJsonConfigString": [
                            '{"query":"select * from t where a=:a","timeoutMs":111,"maxRows":222,"version":3}'
                        ],
                    },
                )
            ]
        if obj == "prsDatastorageTagOperationParameter":
            return [
                (
                    "param-1",
                    None,
                    {
                        "cn": ["a"],
                        "prsActive": ["TRUE"],
                        "prsJsonConfigString": ['{"JSONata":"$.params.a"}'],
                    },
                )
            ]
        return []

    dummy._hierarchy = types.SimpleNamespace(search=_search)
    dummy._meta_cache_get = types.MethodType(_meta_cache_get, dummy)
    dummy._meta_cache_set = types.MethodType(_meta_cache_set, dummy)

    op = asyncio.run(
        DataStoragesAppIntegrationalBase._load_operation_from_link(
            dummy,
            tag_id="tag-1",
            link_id="link-1",
            op_cn="erp.orders.select.v1",
            expected_kind=OperationKind.GET,
        )
    )

    assert op.cn == "erp.orders.select.v1"
    assert op.timeout_ms == 111
    assert op.max_rows == 222
    assert op.version == 3
    assert op.parameters == {"a": {"JSONata": "$.params.a"}}


def test_integrational_load_operation_defaults_active_when_prsactive_missing():
    dummy = types.SimpleNamespace()
    dummy._META_OPERATION_TTL_SEC = 30
    dummy._cache_data = {}
    dummy._safe_json_loads = types.MethodType(DataStoragesAppIntegrationalBase._safe_json_loads, dummy)
    dummy._operation_kind_code = types.MethodType(DataStoragesAppIntegrationalBase._operation_kind_code, dummy)
    dummy._operation_to_cache_payload = types.MethodType(DataStoragesAppIntegrationalBase._operation_to_cache_payload, dummy)
    dummy._meta_cache_key = types.MethodType(DataStoragesAppIntegrationalBase._meta_cache_key, dummy)
    dummy._is_ldap_active = types.MethodType(DataStoragesAppIntegrationalBase._is_ldap_active, dummy)
    dummy._config = types.SimpleNamespace(svc_name="test_integrational")

    async def _meta_cache_get(_self, key: str):
        return _self._cache_data.get(key)

    async def _meta_cache_set(_self, key: str, data: dict, ttl_sec: int):
        _ = ttl_sec
        _self._cache_data[key] = data

    async def _search(payload: dict):
        flt = payload.get("filter") or {}
        obj = (flt.get("objectClass") or [None])[0]
        if obj == "prsDatastorageTagOperation":
            return [
                (
                    "op-node-1",
                    None,
                    {
                        "cn": ["erp.orders.select.v1"],
                        "prsEntityTypeCode": ["0"],
                        "prsJsonConfigString": ['{"query":"select 1","timeoutMs":111,"maxRows":222,"version":3}'],
                    },
                )
            ]
        if obj == "prsDatastorageTagOperationParameter":
            return [
                (
                    "param-1",
                    None,
                    {
                        "cn": ["a"],
                        "prsJsonConfigString": ['{"JSONata":"$.params.a"}'],
                    },
                )
            ]
        return []

    dummy._hierarchy = types.SimpleNamespace(search=_search)
    dummy._meta_cache_get = types.MethodType(_meta_cache_get, dummy)
    dummy._meta_cache_set = types.MethodType(_meta_cache_set, dummy)

    op = asyncio.run(
        DataStoragesAppIntegrationalBase._load_operation_from_link(
            dummy,
            tag_id="tag-1",
            link_id="link-1",
            op_cn="erp.orders.select.v1",
            expected_kind=OperationKind.GET,
        )
    )

    assert op.cn == "erp.orders.select.v1"
    assert op.parameters == {"a": {"JSONata": "$.params.a"}}


