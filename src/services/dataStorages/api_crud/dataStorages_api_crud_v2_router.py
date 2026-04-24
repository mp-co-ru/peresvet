"""
v2 API for dataStorages.

В v2 добавлена поддержка:
- расширенная конфигурация привязки тегов (prsEntityTypeCode/prsJsonConfigString) для интеграционных тегов
- дочерние операции у привязки тега: linkedTags[].operations[].parameters[]

v1 остаётся совместимым со старым контрактом.
"""

import json
from pydantic import BaseModel, Field, ConfigDict, field_validator
from fastapi import APIRouter, Depends, Query

from src.common import api_crud_svc as svc

# используем тот же app (AMQP/handlers) что и у v1
from src.services.dataStorages.api_crud.dataStorages_api_crud_svc import (
    app as dataStorages_api_crud_app,
)


class LinkTagOrAlertAttributesV2(BaseModel):
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

    cn: str | None = Field(None, title="Имя привязки")
    prsStore: dict | None = Field(None, title="Хранилище тега/тревоги")
    prsEntityTypeCode: int | None = Field(
        None,
        title="Код типа привязки",
        description=(
            "Опциональное метаполе. Для интеграционных привязок может быть 2, "
            "но runtime интеграционного сервиса не зависит от этого атрибута."
        ),
    )
    prsJsonConfigString: dict | None = Field(
        None,
        title="Конфигурация привязки",
        description="Для интеграционных тегов: get/set и маппинг параметров.",
    )


def _default_link_attrs_v2() -> "LinkTagOrAlertAttributesV2":
    return LinkTagOrAlertAttributesV2.model_validate({})


class LinkTagV2(BaseModel):
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

    tagId: str = Field(title="Идентификатор привязываемого тега")
    attributes: LinkTagOrAlertAttributesV2 = Field(default_factory=_default_link_attrs_v2)
    operations: list["LinkTagOperationV2"] = Field(
        default_factory=list,
        title="Операции, связанные с привязкой тега",
    )


class LinkAlertV2(BaseModel):
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

    alertId: str = Field(title="Идентификатор привязываемой тревоги")
    attributes: LinkTagOrAlertAttributesV2 = Field(default_factory=_default_link_attrs_v2)


class LinkTagOperationParameterAttributesV2(BaseModel):
    model_config = ConfigDict(protected_namespaces=(), extra="allow")

    cn: str = Field(title="Имя параметра операции (CN)")
    description: str | None = Field(
        None,
        title="Описание",
        description="Текст для операторов: что передаётся в параметре.",
    )
    prsActive: bool = Field(True, title="Флаг активности параметра")
    prsJsonConfigString: dict | None = Field(default_factory=dict, title="Конфигурация параметра")


def _default_link_tag_operation_parameter_attrs_v2() -> "LinkTagOperationParameterAttributesV2":
    return LinkTagOperationParameterAttributesV2.model_validate({})


class LinkTagOperationParameterV2(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    attributes: LinkTagOperationParameterAttributesV2 = Field(
        default_factory=_default_link_tag_operation_parameter_attrs_v2
    )


class LinkTagOperationAttributesV2(BaseModel):
    model_config = ConfigDict(protected_namespaces=(), extra="allow")

    cn: str = Field(title="Имя операции (CN)")
    prsActive: bool = Field(True, title="Флаг активности операции")
    prsEntityTypeCode: int = Field(0, title="Тип операции", description="0 - GET, 1 - SET")
    prsJsonConfigString: dict | None = Field(
        default_factory=dict,
        title="Конфигурация операции",
        description="Ожидаются ключи: query, timeoutMs, maxRows, version.",
    )


def _default_link_tag_operation_attrs_v2() -> "LinkTagOperationAttributesV2":
    return LinkTagOperationAttributesV2.model_validate({})


class LinkTagOperationV2(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    attributes: LinkTagOperationAttributesV2 = Field(default_factory=_default_link_tag_operation_attrs_v2)
    parameters: list[LinkTagOperationParameterV2] = Field(default_factory=list, title="Параметры операции")


LinkTagV2.model_rebuild()


class DataStorageAttributesV2(svc.NodeAttributes):
    pass


class DataStorageCreateV2(svc.NodeCreate):
    attributes: DataStorageAttributesV2 = Field(title="Атрибуты хранилища")
    linkedTags: list[LinkTagV2] = Field(default_factory=list, title="Список привязываемых тегов")
    linkedAlerts: list[LinkAlertV2] = Field(default_factory=list, title="Список привязываемых тревог")

    @field_validator("attributes")
    @classmethod
    def ds_type_is_necessary(cls, v: DataStorageAttributesV2) -> DataStorageAttributesV2:
        if v.prsEntityTypeCode is None:
            v.prsEntityTypeCode = 0
        return v


class DataStorageReadV2(svc.NodeRead):
    getLinkedTags: bool = Field(False, title="Возврат присоединённых тегов")
    getLinkedAlerts: bool = Field(False, title="Возврат присоединённых тревог")


class OneDataStorageInReadResultV2(svc.OneNodeInReadResult):
    linkedTags: list[LinkTagV2] | None = Field(None, title="Список присоединённых тегов")
    linkedAlerts: list[LinkAlertV2] | None = Field(None, title="Список присоединённых тревог")


class DataStorageReadResultV2(svc.NodeReadResult):
    data: list[OneDataStorageInReadResultV2] = Field(title="Список хранилищ данных.")


class DataStorageUpdateV2(DataStorageCreateV2):
    id: str = Field(title="Идентификатор изменяемого узла.", description="GUID")
    attributes: DataStorageAttributesV2 | None = Field(None, title="Атрибуты хранилища")

    unlinkTags: list[str] | None = Field(default_factory=list, title="Список id тегов.")
    unlinkAlerts: list[str] | None = Field(default_factory=list, title="Список id тревог.")

    @field_validator("id")
    @classmethod
    def validate_id(cls, v):
        return svc.valid_uuid(v)


router_v2 = APIRouter(prefix="/v2/dataStorages")
error_handler = svc.ErrorHandler()


@router_v2.get("/", response_model=DataStorageReadResultV2 | None, status_code=200, response_model_exclude_none=True)
async def read_v2(
    q: str | None = None,
    payload: DataStorageReadV2 | None = None,
    id: list[str] | None = Query(None),
    base: str | None = None,
    deref: bool | None = None,
    scope: int | None = None,
    hierarchy: bool | None = None,
    getParent: bool | None = None,
    attributes: list[str] | None = Query(None),
    filter: str | None = None,
    getLinkedTags: bool | None = None,
    getLinkedAlerts: bool | None = None,
    error_handler: svc.ErrorHandler = Depends(),
):
    def _is_fastapi_param_placeholder(value) -> bool:
        return getattr(value, "__class__", None).__module__.startswith("fastapi.")

    # Поддерживаем и legacy q=<json>, и обычные query-параметры.
    if payload is None and not q:
        query_payload: dict = {}
        if id is not None and not _is_fastapi_param_placeholder(id):
            query_payload["id"] = id
        if base is not None:
            query_payload["base"] = base
        if deref is not None:
            query_payload["deref"] = deref
        if scope is not None:
            query_payload["scope"] = scope
        if hierarchy is not None:
            query_payload["hierarchy"] = hierarchy
        if getParent is not None:
            query_payload["getParent"] = getParent
        if attributes is not None and not _is_fastapi_param_placeholder(attributes):
            query_payload["attributes"] = attributes
        if filter is not None:
            try:
                query_payload["filter"] = json.loads(filter)
            except Exception as ex:
                res = {"error": {"code": 422, "message": f"Некорректный filter: {ex}"}}
                await error_handler.handle_error(res)
                return {}
        if getLinkedTags is not None:
            query_payload["getLinkedTags"] = getLinkedTags
        if getLinkedAlerts is not None:
            query_payload["getLinkedAlerts"] = getLinkedAlerts

        if query_payload:
            payload = DataStorageReadV2.model_validate(query_payload)

    res = await dataStorages_api_crud_app.api_get_read(DataStorageReadV2, q, payload)
    await error_handler.handle_error(res)
    return res


@router_v2.post("/", response_model=svc.NodeCreateResult, status_code=201)
async def create_v2(payload: dict | None = None, error_handler: svc.ErrorHandler = Depends()):
    if payload is None:
        payload = {}
    try:
        svc.coerce_prs_json_strings_in_mapping_tree(payload)
        p = DataStorageCreateV2.model_validate_json(json.dumps(payload))
    except Exception as ex:
        res = {"error": {"code": 422, "message": f"Несоответствие входных данных: {ex}"}}
        dataStorages_api_crud_app._logger.exception(res)
        await error_handler.handle_error(res)
        return {}

    res = await dataStorages_api_crud_app._create(p)
    await error_handler.handle_error(res)
    return res


@router_v2.put("/", status_code=202)
async def update_v2(payload: dict, error_handler: svc.ErrorHandler = Depends()):
    try:
        svc.coerce_prs_json_strings_in_mapping_tree(payload)
        DataStorageUpdateV2.model_validate(payload)
    except Exception as ex:
        res = {"error": {"code": 422, "message": f"Несоответствие входных данных: {ex}"}}
        dataStorages_api_crud_app._logger.exception(res)
        await error_handler.handle_error(res)
        return {}

    res = await dataStorages_api_crud_app._update(payload=payload)
    await error_handler.handle_error(res)
    return res

