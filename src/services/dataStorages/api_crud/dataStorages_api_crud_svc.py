"""
Модуль содержит классы, описывающие входные данные для команд CRUD для хранилищ данных
и класс сервиса ``dataStorages_api_crud_svc``.
"""
import sys
from typing import List
from pydantic import BaseModel, Field, validator
from fastapi import APIRouter

sys.path.append(".")

from src.common import api_crud_svc as svc
from dataStorages_api_crud_settings import DataStoragesAPICRUDSettings

class LinkTagOrAlertAttributes(BaseModel):
    prsStore: dict = Field(None, title="Хранилище тега")

class LinkTag(BaseModel):
    tagId: str = Field(title="Идентификатор привязываемого тега")
    attributes: LinkTagOrAlertAttributes = Field({})

class LinkAlert(BaseModel):
    alertId: str = Field(title="Идентификатор привязываемой тревоги")
    attributes: LinkTagOrAlertAttributes = Field({})

class DataStorageAttributes(svc.NodeAttributes):
    pass

class DataStorageCreate(svc.NodeCreate):
    attributes: DataStorageAttributes = Field(title="Атрибуты узла")
    linkTags: List[LinkTag] = Field([], title="Список привязываемых тегов")
    linkAlerts: List[LinkAlert] = Field([], title="Список привязываемых тревог")

    @validator('attributes')
    @classmethod
    def ds_type_is_necessary(cls, v: DataStorageAttributes) -> DataStorageAttributes:
        # если не указан тип базы данных, то по умолчанию используется
        # PostgreSQL
        if v.prsEntityTypeCode is None:
            v.prsEntityTypeCode = 0

        return v

class DataStorageRead(svc.NodeRead):
    getLinkedTags: bool = Field(
        False,
        title="Флаг возврата присоединённых тегов"
    )
    getLinkedAlerts: bool = Field(
        False,
        title="Флаг возврата присоединённых тревог"
    )

class OneDataStorageInReadResult(svc.OneNodeInReadResult):
    linkedTags: List[str] = Field(
        None,
        title="Список id присоединённых тегов."
    )
    linkedAlerts: List[str] = Field(
        None,
        title="Список id присоединённых тревог."
    )

class DataStorageReadResult(svc.NodeReadResult):
    data: List[OneDataStorageInReadResult] = Field(title="Список хранилищ данных.")

class DataStorageUpdate(DataStorageCreate):
    id: str = Field(title="Идентификатор изменяемого узла.",
                    description="Должен быть в формате GUID.")
    attributes: DataStorageAttributes = Field(None, title="Атрибуты узла")
    unlinkTags: List[str] = Field(
        None,
        title="Список id тегов."
    )
    unlinkAlerts: List[str] = Field(
        None,
        title="Список id тревог."
    )

    validate_id = validator('id', allow_reuse=True)(svc.valid_uuid)

class DataStoragesAPICRUD(svc.APICRUDSvc):
    """Сервис работы с хранилищами данных в иерархии.

    Подписывается на очередь ``dataStorages_api_crud`` обменника ``dataStorages_api_crud``,
    в которую публикует сообщения сервис ``dataStorages_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    _outgoing_commands = {
        "create": "dataStorages.create",
        "read": "dataStorages.read",
        "update": "dataStorages.update",
        "delete": "dataStorages.delete"
    }

    def __init__(self, settings: DataStoragesAPICRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def create(self, payload: DataStorageCreate) -> dict:
        return await super().create(payload=payload)

    async def read(self, payload: DataStorageRead) -> dict:
        return await super().read(payload=payload)

    async def update(self, payload: DataStorageUpdate) -> dict:
        return await super().update(payload=payload)

settings = DataStoragesAPICRUDSettings()

app = DataStoragesAPICRUD(settings=settings, title="`DataStoragesAPICRUD` service")

router = APIRouter()

@router.post("/", response_model=svc.NodeCreateResult, status_code=201)
async def create(payload: DataStorageCreate):
    return await app.create(payload)

@router.get("/", response_model=svc.NodeReadResult, status_code=200)
async def read(payload: DataStorageRead):
    return await app.read(payload)

@router.put("/", status_code=202)
async def update(payload: DataStorageUpdate):
    await app.update(payload)

@router.delete("/", status_code=202)
async def delete(payload: DataStorageRead):
    await app.delete(payload)

app.include_router(router, prefix=f"{settings.api_version}/dataStorages", tags=["dataStorages"])
