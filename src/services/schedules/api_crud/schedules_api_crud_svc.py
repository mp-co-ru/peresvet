"""
Модуль содержит классы, описывающие входные данные для команд CRUD для расписаний
и класс сервиса ``schedules_api_crud_svc``.
"""
import sys
from uuid import UUID
from typing import Any, List
from pydantic import Field, validator

from fastapi import APIRouter

sys.path.append(".")

from src.common import api_crud_svc as svc
from schedules_api_crud_settings import SchedulesAPICRUDSettings

class TagCreateAttributes(svc.NodeCreateAttributes):
    pass

class ScheduleCreate(svc.NodeCreate):
    attributes: TagCreateAttributes = Field(title="Атрибуты узла")

    # validate_id = validator('parentId', 'dataStorageId', 'connectorId', allow_reuse=True)(svc.valid_uuid)

class ScheduleRead(svc.NodeRead):
    pass

class OneScheduleInReadResult(svc.OneNodeInReadResult):
    pass

class ScheduleReadResult(svc.NodeReadResult):
    data: List[OneScheduleInReadResult] = Field(title="Список расписаний.")
    pass

class ScheduleUpdate(svc.NodeUpdate):
    pass

class SchedulesAPICRUD(svc.APICRUDSvc):
    """Сервис работы с расписаниями в иерархии.

    Подписывается на очередь ``schedules_api_crud`` обменника ``schedules_api_crud``,
    в которую публикует сообщения сервис ``schedules_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: SchedulesAPICRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def create(self, payload: ScheduleCreate) -> dict:
        return await super().create(payload=payload)

    async def read(self, payload: ScheduleRead) -> dict:
        return await super().read(payload=payload)

    async def update(self, payload: ScheduleUpdate) -> dict:
        return await super().update(payload=payload)

settings = SchedulesAPICRUDSettings()

app = SchedulesAPICRUD(settings=settings, title="`SchedulesAPICRUD` service")

router = APIRouter()

@router.post("/", response_model=svc.NodeCreateResult, status_code=201)
async def create(payload: ScheduleCreate):
    return await app.create(payload)

@router.get("/", response_model=svc.NodeReadResult, status_code=200)
async def read(payload: ScheduleRead):
    return await app.read(payload)

@router.put("/", status_code=202)
async def update(payload: ScheduleUpdate):
    await app.update(payload)

@router.delete("/", status_code=202)
async def delete(payload: ScheduleRead):
    await app.delete(payload)

app.include_router(router, prefix=f"{settings.api_version}/schedules", tags=["schedules"])
