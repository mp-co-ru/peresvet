"""
Модуль содержит классы, описывающие входные данные для команд CRUD для хранилищ данных
и класс сервиса ``dataStorages_api_crud_svc``.
"""
import sys
from uuid import UUID
from typing import Any, List
from pydantic import Field, validator

from fastapi import APIRouter

sys.path.append(".")

from src.common import api_crud_svc as svc
from dataStorages_api_crud_settings import DataStoragesAPICRUDSettings

class DataStorageCreateAttributes(svc.NodeAttributes):
    pass

class DataStorageCreate(svc.NodeCreate):
    attributes: DataStorageCreateAttributes = Field(title="Атрибуты узла")

    # validate_id = validator('parentId', 'dataStorageId', 'connectorId', allow_reuse=True)(svc.valid_uuid)

class DataStorageRead(svc.NodeRead):
    pass

class OneDataStorageInReadResult(svc.OneNodeInReadResult):
    pass

class DataStorageReadResult(svc.NodeReadResult):
    data: List[OneDataStorageInReadResult] = Field(title="Список хранилищ данных.")
    pass

class DataStorageUpdate(svc.NodeUpdate):
    pass

class DataStoragesAPICRUD(svc.APICRUDSvc):
    """Сервис работы с хранилищами данных в иерархии.

    Подписывается на очередь ``dataStorages_api_crud`` обменника ``dataStorages_api_crud``,
    в которую публикует сообщения сервис ``dataStorages_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

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
