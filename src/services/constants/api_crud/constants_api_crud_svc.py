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
from constants_api_crud_settings import ConstantsAPICRUDSettings

class ConstantCreateAttributes(svc.NodeAttributes):
    prsValueTypeCode: int = Field(
        2,
        title="Тип значений константы.",
        description=(
            "0 - целое, 1 - вещественное, 2 - строковое, 3 - дискретное, "
            "4 - json"
        )
    )

    prsConstantValue: str = Field(
        "",
        title="Значение константы",
        description=""
    )

class ConstantCreate(svc.NodeCreate):

    attributes: ConstantCreateAttributes = Field(title="Атрибуты узла")

    # validate_id = validator('parentId', 'dataStorageId', 'connectorId', allow_reuse=True)(svc.valid_uuid)

class ConstantRead(svc.NodeRead):
    pass

class OneConstantInReadResult(svc.OneNodeInReadResult):
    pass

class ConstantReadResult(svc.NodeReadResult):
    data: List[OneConstantInReadResult] = Field(title="Список констант.")
    pass

class ConstantUpdate(svc.NodeUpdate):
    pass

class ConstantsAPICRUD(svc.APICRUDSvc):
    """Сервис работы с константами в иерархии.

    Подписывается на очередь ``consts_api_crud`` обменника ``consts_api_crud``,
    в которую публикует сообщения сервис ``consts_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: ConstantsAPICRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def create(self, payload: ConstantCreate) -> dict:
        return await super().create(payload=payload)

    async def read(self, payload: ConstantRead) -> dict:
        return await super().read(payload=payload)

    async def update(self, payload: ConstantUpdate) -> dict:
        return await super().update(payload=payload)

settings = ConstantsAPICRUDSettings()

app = ConstantsAPICRUD(settings=settings, title="`ConstantsAPICRUD` service")

router = APIRouter()

@router.post("/", response_model=svc.NodeCreateResult, status_code=201)
async def create(payload: ConstantCreate):
    return await app.create(payload)

@router.get("/", response_model=svc.NodeReadResult, status_code=200)
async def read(payload: ConstantRead):
    return await app.read(payload)

@router.put("/", status_code=202)
async def update(payload: ConstantUpdate):
    await app.update(payload)

@router.delete("/", status_code=202)
async def delete(payload: ConstantRead):
    await app.delete(payload)

app.include_router(router, prefix=f"{settings.api_version}/constants", tags=["constants"])
