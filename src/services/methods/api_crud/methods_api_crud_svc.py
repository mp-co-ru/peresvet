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
from src.services.methods.api_crud.methods_api_crud_settings import MethodsAPICRUDSettings

class MethodCreateAttributes(svc.NodeAttributes):
    prsMethodAddress: str = Field(title="Адрес метода")
    prsEntityTypeCode: int = Field(0, title="Тип метода")

class MethodParameter(svc.NodeCreate):
    pass

class MethodCreate(svc.NodeCreate):
    attributes: MethodCreateAttributes = Field({}, title="Атрибуты метода")
    initiatedBy: str | list[str] = Field([], title="Список id экземпляров сущностей, инициирующих вычисление тега.")
    parameters: List[MethodParameter] = Field(
        [],
        title="Параметры метода.",
        description=(
            "При создании параметров метода они должны быть пронумерованы ",
            "с помощью атрибута prsIndex. В противном случае параметры ",
            "будут переданы в вычислительный метод в случайном порядке."
        )
    )

    @validator('initiatedBy')
    @classmethod
    def make_initiatedBy_as_array(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [v]
        return v

class MethodRead(svc.NodeRead):
    pass

class MethodUpdate(MethodCreate):
    pass

class MethodsAPICRUD(svc.APICRUDSvc):
    """Сервис работы с методами в иерархии.

    Формат ожидаемых сообщений

    """

    _outgoing_commands = {
        "create": "methods.create",
        "read": "methods.read",
        "update": "methods.update",
        "delete": "methods.delete"
    }

    def __init__(self, settings: MethodsAPICRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def create(self, payload: MethodCreate) -> dict:
        return await super().create(payload=payload)

    async def read(self, payload: MethodRead) -> dict:
        return await super().read(payload=payload)

    async def update(self, payload: MethodUpdate) -> dict:
        return await super().update(payload=payload)

settings = MethodsAPICRUDSettings()

app = MethodsAPICRUD(settings=settings, title="`MethodsAPICRUD` service")

router = APIRouter()

@router.post("/", response_model=svc.NodeCreateResult, status_code=201)
async def create(payload: MethodCreate):
    return await app.create(payload)

@router.get("/", response_model=svc.NodeReadResult, status_code=200)
async def read(payload: MethodRead):
    return await app.read(payload)

@router.put("/", status_code=202)
async def update(payload: MethodUpdate):
    await app.update(payload)

@router.delete("/", status_code=202)
async def delete(payload: svc.NodeDelete):
    await app.delete(payload)

app.include_router(router, prefix=f"{settings.api_version}/methods", tags=["methods"])
