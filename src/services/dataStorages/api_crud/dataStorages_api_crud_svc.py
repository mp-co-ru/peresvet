"""
Модуль содержит примеры запросов и ответов на них, параметров которые могут входить в
запрос, в сервисе dataStorages.
"""
import sys
import json
from pydantic import BaseModel, Field, field_validator, ConfigDict
from fastapi import APIRouter, Depends, Query

sys.path.append(".")

from src.common import api_crud_svc as svc
from src.services.dataStorages.api_crud.dataStorages_api_crud_settings import DataStoragesAPICRUDSettings

class LinkTagOrAlertAttributes(BaseModel):
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

    cn: str = Field(title="Имя привязки")
    prsStore: dict | None = Field(None, title="Хранилище тега/тревоги")

def _default_link_attrs() -> "LinkTagOrAlertAttributes":
    return LinkTagOrAlertAttributes.model_validate({"cn": ""})

class LinkTag(BaseModel):
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

    tagId: str = Field(title="Идентификатор привязываемого тега")
    attributes: LinkTagOrAlertAttributes = Field(default_factory=_default_link_attrs)

class LinkAlert(BaseModel):
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

    alertId: str = Field(title="Идентификатор привязываемой тревоги")
    attributes: LinkTagOrAlertAttributes = Field(default_factory=_default_link_attrs)

class DataStorageAttributes(svc.NodeAttributes):
    pass

class DataStorageCreate(svc.NodeCreate):
    attributes: DataStorageAttributes = Field(title="Атрибуты хранилища")
    linkedTags: list[LinkTag] = Field(default_factory=list, title="Список привязываемых тегов")
    linkedAlerts: list[LinkAlert] = Field(default_factory=list, title="Список привязываемых тревог")
    # unlinkTags: list[LinkTag] | None = Field([], title="Список id тегов.")

    @field_validator("attributes")
    @classmethod
    def ds_type_is_necessary(cls, v: DataStorageAttributes) -> DataStorageAttributes:
        # если не указан тип базы данных, то по умолчанию используется
        # PostgreSQL
        if v.prsEntityTypeCode is None:
            v.prsEntityTypeCode = 0

        return v

class  DataStorageRead(svc.NodeRead):
    getLinkedTags: bool = Field(
        False,
        title="Флаг возврата присоединённых тегов"
    )
    getLinkedAlerts: bool = Field(
        False,
        title="Флаг возврата присоединённых тревог"
    )

class OneDataStorageInReadResult(svc.OneNodeInReadResult):
    linkedTags: list[LinkTag] | None = Field(
        None,
        title="Список id присоединённых тегов."
    )
    linkedAlerts: list[LinkAlert] | None = Field(
        None,
        title="Список id присоединённых тревог."
    )

class DataStorageReadResult(svc.NodeReadResult):
    data: list[OneDataStorageInReadResult] = Field(title="Список хранилищ данных.")

class DataStorageUpdate(DataStorageCreate):
    id: str = Field(title="Идентификатор изменяемого узла.",
                    description="Должен быть в формате GUID.")

    attributes: DataStorageAttributes | None = Field(None, title="Атрибуты хранилища")

    unlinkTags: list[str] | None = Field(
        default_factory=list,
        title="Список id тегов."
    )
    unlinkAlerts: list[str] | None = Field(
        default_factory=list,
        title="Список id тревог."
    )

    @field_validator("id")
    @classmethod
    def validate_id(cls, v):
        return svc.valid_uuid(v)

class DataStoragesAPICRUD(svc.APICRUDSvc):
    """Сервис работы с хранилищами данных в иерархии.

    Подписывается на очередь ``dataStorages_api_crud`` обменника ``dataStorages_api_crud``,
    в которую публикует сообщения сервис ``dataStorages_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """
    def __init__(self, settings: DataStoragesAPICRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def _create(self, payload: DataStorageCreate) -> dict:
        return await super()._create(payload=payload)

    async def _read(self, payload: DataStorageRead) -> dict:
        return await super()._read(payload=payload)

    async def _update(self, payload: dict) -> dict:
        return await super()._update(payload=payload)

settings = DataStoragesAPICRUDSettings()

app = DataStoragesAPICRUD(settings=settings, title="`DataStoragesAPICRUD` service")

router = APIRouter(prefix=f"{settings.api_version}/dataStorages")

error_handler = svc.ErrorHandler()

@router.get("/", response_model=DataStorageReadResult | None, status_code=200, response_model_exclude_none=True)
async def read(
    id: list[str] | None = Query(None),
    base: str | None = None,
    deref: bool = True,
    scope: int = 1,
    hierarchy: bool = False,
    getParent: bool = False,
    attributes: list[str] | None = Query(None),
    filter: str | None = None,
    getLinkedTags: bool = False,
    getLinkedAlerts: bool = False,
    q: str | None = None,
    payload: DataStorageRead | None = None,
    error_handler: svc.ErrorHandler = Depends(),
):
    if q is not None or payload is not None:
        res = await app.api_get_read(DataStorageRead, q, payload)
    else:
        body: dict = {
            "deref": deref,
            "scope": scope,
            "hierarchy": hierarchy,
            "getParent": getParent,
            "getLinkedTags": getLinkedTags,
            "getLinkedAlerts": getLinkedAlerts,
        }
        if id is not None:
            body["id"] = id
        if base is not None:
            body["base"] = base
        if attributes is not None:
            body["attributes"] = attributes
        if filter is not None:
            body["filter"] = json.loads(filter)
        p = DataStorageRead.model_validate(body)
        res = await app._read(p)
    await error_handler.handle_error(res)
    return res

@router.post("/", response_model=svc.NodeCreateResult, status_code=201)
async def create(payload: dict | None = None, error_handler: svc.ErrorHandler = Depends()):
    if payload is None:
        payload = {}

    try:
        p = DataStorageCreate.model_validate_json(json.dumps(payload))
    except Exception as ex:
        res = {"error": {"code": 422, "message": f"Несоответствие входных данных: {ex}"}}
        app._logger.exception(res)
        await error_handler.handle_error(res)
        return {}

    res = await app._create(p)
    await error_handler.handle_error(res)
    return res

@router.put("/", status_code=202)
async def update(payload: dict, error_handler: svc.ErrorHandler = Depends()):
    try:
        DataStorageUpdate.model_validate(payload)
    except Exception as ex:
        res = {"error": {"code": 422, "message": f"Несоответствие входных данных: {ex}"}}
        app._logger.exception(res)
        await error_handler.handle_error(res)
        return {}

    res = await app._update(payload=payload)
    await error_handler.handle_error(res)
    return res

app.include_router(router, tags=["dataStorages"])
