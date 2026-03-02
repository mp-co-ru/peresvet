"""
v2 API for dataStorages.

В v2 добавлена поддержка:
- operations (cn=system/operations) в create/update/read
- расширенная конфигурация привязки тегов (prsEntityTypeCode/prsJsonConfigString) для интеграционных тегов

v1 остаётся совместимым со старым контрактом.
"""

import json
from pydantic import BaseModel, Field, ConfigDict, field_validator
from fastapi import APIRouter, Depends

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
        description="Для интеграционных тегов устанавливается 2.",
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


class LinkAlertV2(BaseModel):
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

    alertId: str = Field(title="Идентификатор привязываемой тревоги")
    attributes: LinkTagOrAlertAttributesV2 = Field(default_factory=_default_link_attrs_v2)


class DataStorageOperationParameterV2(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    cn: str = Field(title="Имя параметра операции (CN)")
    prsActive: bool = Field(True, title="Флаг активности параметра")
    prsJsonConfigString: dict | None = Field(default_factory=dict, title="Конфигурация параметра")


class DataStorageOperationV2(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    cn: str = Field(title="Имя операции (CN)")
    prsActive: bool = Field(True, title="Флаг активности операции")
    prsEntityTypeCode: int = Field(0, title="Тип операции", description="0 - GET, 1 - SET")
    prsJsonConfigString: dict | None = Field(default_factory=dict, title="Конфигурация операции")
    parameters: list[DataStorageOperationParameterV2] = Field(default_factory=list, title="Параметры операции")


class DataStorageAttributesV2(svc.NodeAttributes):
    pass


class DataStorageCreateV2(svc.NodeCreate):
    attributes: DataStorageAttributesV2 = Field(title="Атрибуты хранилища")
    linkTags: list[LinkTagV2] = Field(default_factory=list, title="Список привязываемых тегов")
    linkAlerts: list[LinkAlertV2] = Field(default_factory=list, title="Список привязываемых тревог")
    operations: list[DataStorageOperationV2] = Field(default_factory=list, title="Список операций")

    @field_validator("attributes")
    @classmethod
    def ds_type_is_necessary(cls, v: DataStorageAttributesV2) -> DataStorageAttributesV2:
        if v.prsEntityTypeCode is None:
            v.prsEntityTypeCode = 0
        return v


class DataStorageReadV2(svc.NodeRead):
    getLinkedTags: bool = Field(False, title="Возврат присоединённых тегов")
    getLinkedAlerts: bool = Field(False, title="Возврат присоединённых тревог")
    getLinkedOperations: bool = Field(False, title="Возврат операций", description="cn=system/operations")


class OneDataStorageInReadResultV2(svc.OneNodeInReadResult):
    linkedTags: list[LinkTagV2] | None = Field(None, title="Список присоединённых тегов")
    linkedAlerts: list[LinkAlertV2] | None = Field(None, title="Список присоединённых тревог")
    operations: list[DataStorageOperationV2] | None = Field(None, title="Список операций")


class DataStorageReadResultV2(svc.NodeReadResult):
    data: list[OneDataStorageInReadResultV2] = Field(title="Список хранилищ данных.")


class DataStorageUpdateV2(DataStorageCreateV2):
    id: str = Field(title="Идентификатор изменяемого узла.", description="GUID")
    attributes: DataStorageAttributesV2 | None = Field(None, title="Атрибуты хранилища")

    unlinkTags: list[str] | None = Field(default_factory=list, title="Список id тегов.")
    unlinkAlerts: list[str] | None = Field(default_factory=list, title="Список id тревог.")
    unlinkOperations: list[str] | None = Field(default_factory=list, title="Список CN операций для удаления.")

    @field_validator("id")
    @classmethod
    def validate_id(cls, v):
        return svc.valid_uuid(v)


router_v2 = APIRouter(prefix="/v2/dataStorages")
error_handler = svc.ErrorHandler()


@router_v2.get("/", response_model=DataStorageReadResultV2 | None, status_code=200, response_model_exclude_none=True)
async def read_v2(q: str | None = None, payload: DataStorageReadV2 | None = None, error_handler: svc.ErrorHandler = Depends()):
    # переходный период: поддержим q, но основной путь — payload/отдельные ключи (см. будущую правку GET).
    res = await dataStorages_api_crud_app.api_get_read(DataStorageReadV2, q, payload)
    await error_handler.handle_error(res)
    return res


@router_v2.post("/", response_model=svc.NodeCreateResult, status_code=201)
async def create_v2(payload: dict | None = None, error_handler: svc.ErrorHandler = Depends()):
    if payload is None:
        payload = {}
    try:
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
        DataStorageUpdateV2.model_validate(payload)
    except Exception as ex:
        res = {"error": {"code": 422, "message": f"Несоответствие входных данных: {ex}"}}
        dataStorages_api_crud_app._logger.exception(res)
        await error_handler.handle_error(res)
        return {}

    res = await dataStorages_api_crud_app._update(payload=payload)
    await error_handler.handle_error(res)
    return res

