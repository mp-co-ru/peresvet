"""
Модуль содержит классы, описывающие входные данные для команд CRUD для коннекторов
и класс сервиса ``connectors_api_crud_svc``.
"""
import sys
from uuid import UUID
from typing import Any, List
from pydantic import Field, validator

from fastapi import APIRouter

sys.path.append(".")

from src.common import api_crud_svc as svc
from connectors_api_crud_settings import ConnectorsAPICRUDSettings

class TagCreateAttributes(svc.NodeCreateAttributes):
    pass

class ConnectorCreate(svc.NodeCreate):
    attributes: TagCreateAttributes = Field(title="Атрибуты узла")

    # validate_id = validator('parentId', 'dataStorageId', 'connectorId', allow_reuse=True)(svc.valid_uuid)

class ConnectorRead(svc.NodeRead):
    pass

class OneConnectorInReadResult(svc.OneNodeInReadResult):
    pass

class ConnectorReadResult(svc.NodeReadResult):
    data: List[OneConnectorInReadResult] = Field(title="Список коннекторов.")
    pass

# class ConnectorUpdate(svc.NodeUpdate):
#     pass

class ConnectorsAPICRUD(svc.APICRUDSvc):
    """Сервис работы с коннекторами в иерархии.

    Подписывается на очередь ``connectors_api_crud`` обменника ``connectors_api_crud``,
    в которую публикует сообщения сервис ``connectors_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: ConnectorsAPICRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def create(self, payload: ConnectorCreate) -> dict:
        return await super().create(payload=payload)

    async def read(self, payload: ConnectorRead) -> dict:
        return await super().read(payload=payload)

    # async def update(self, payload: ConnectorUpdate) -> dict:
    #     return await super().update(payload=payload)

settings = ConnectorsAPICRUDSettings()

app = ConnectorsAPICRUD(settings=settings, title="`ConnectorsAPICRUD` service")

router = APIRouter()

@router.post("/", response_model=svc.NodeCreateResult, status_code=201)
async def create(payload: ConnectorCreate):
    return await app.create(payload)

@router.get("/", response_model=svc.NodeCreateResult, status_code=201)
async def read(payload: ConnectorRead):
    return await app.create(payload)

# @router.put("/", status_code=202)
# async def update(payload: ConnectorUpdate):
#     await app.update(payload)

@router.delete("/", status_code=202)
async def delete(payload: ConnectorRead):
    await app.delete(payload)

app.include_router(router, prefix=f"{settings.api_version}/connectors", tags=["connectors"])
