"""
Модуль содержит классы, описывающие входные данные для команд CRUD для констант
и класс сервиса ``consts_api_crud_svc``.
"""
import sys
from uuid import UUID
from typing import Any, List
from pydantic import Field, validator

from fastapi import APIRouter

sys.path.append(".")

from src.common import api_crud_svc as svc
from consts_api_crud_settings import ConstsAPICRUDSettings

class ConstCreateAttributes(svc.NodeCreateAttributes):
    prsValueTypeCode: int = Field(
        2,
        title="Тип значений константы.",
        description=(
            "0 - целое, 1 - вещественное, 2 - строковое, 3 - дискретное, "
            "4 - json"
        )
    )

    prsConstValue: str = Field(
        "",
        title="Значение константы",
        description=""
    )

class ConstCreate(svc.NodeCreate):

    attributes: ConstCreateAttributes = Field(title="Атрибуты узла")

    # validate_id = validator('parentId', 'dataStorageId', 'connectorId', allow_reuse=True)(svc.valid_uuid)

class ConstRead(svc.NodeRead):
    pass

class OneConstInReadResult(svc.OneNodeInReadResult):
    pass

class ConstReadResult(svc.NodeReadResult):
    data: List[OneConstInReadResult] = Field(title="Список констант.")
    pass

class ConstUpdate(svc.NodeUpdate):
    pass

class ConstsAPICRUD(svc.APICRUDSvc):
    """Сервис работы с константами в иерархии.

    Подписывается на очередь ``consts_api_crud`` обменника ``consts_api_crud``,
    в которую публикует сообщения сервис ``consts_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: ConstsAPICRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def create(self, payload: ConstCreate) -> dict:
        return await super().create(payload=payload)

    async def read(self, payload: ConstRead) -> dict:
        return await super().read(payload=payload)

    async def update(self, payload: ConstUpdate) -> dict:
        return await super().update(payload=payload)

settings = ConstsAPICRUDSettings()

app = ConstsAPICRUD(settings=settings, title="`ConstsAPICRUD` service")

router = APIRouter()

@router.post("/", response_model=svc.NodeCreateResult, status_code=201)
async def create(payload: ConstCreate):
    return await app.create(payload)

@router.get("/", response_model=svc.NodeReadResult, status_code=200)
async def read(payload: ConstRead):
    return await app.read(payload)

@router.put("/", status_code=202)
async def update(payload: ConstUpdate):
    await app.update(payload)

@router.delete("/", status_code=202)
async def delete(payload: ConstRead):
    await app.delete(payload)

app.include_router(router, prefix=f"{settings.api_version}/consts", tags=["consts"])
