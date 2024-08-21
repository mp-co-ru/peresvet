"""
Модуль содержит примеры запросов и ответов на них, параметров которые могут входить в
запрос, в сервисе methods.
"""
import json
import sys
from typing import List
from pydantic import BaseModel, Field, validator
from fastapi import APIRouter, Depends, HTTPException

sys.path.append(".")

from src.common import api_crud_svc as svc
from src.services.methods.api_crud.methods_api_crud_settings import MethodsAPICRUDSettings

class MethodCreateAttributes(svc.NodeAttributes):
    prsMethodAddress: str = Field(title="Адрес метода", required=True)
    prsEntityTypeCode: int = Field(0, title="Тип метода")

class MethodParameter(svc.NodeCreate):
    pass

class MethodCreate(svc.NodeCreate):
    attributes: MethodCreateAttributes = Field(title="Атрибуты метода", required=True)
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
    # не было поля для id, для обновляемого метода
    id: str = Field(title="id обновляемого метода")

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

router = APIRouter(prefix=f"{settings.api_version}/methods")

error_handler = svc.ErrorHandler()

@router.post("/", response_model=svc.NodeCreateResult, status_code=201)
async def create(payload: MethodCreate, error_handler: svc.ErrorHandler = Depends()):
    """
    Метод добавляет метод в иерархию.

    **Запрос:**

        .. http:example::
            :request: ../../../../docs/source/samples/methods/addMethodIn.txt
            :response: ../../../../docs/source/samples/methods/addMethodOut.txt

        * **parentId** (str) - Id родительского узла. Обязательное поле.
        * **initiatedBy** (str | list[str]) - Список id экземпляров сущностей,
          инициирующих вычисление тега. Необязательный атрибут.
        * **attributes** (dict) - Атрибуты метода. Обязательное поле. Включает в себя:

          * **prsMethodAddress** (str) - Адрес метода. Обязательное поле.
          * **prsEntityTypeCode** (int) - Тип метода. Необязательное поле.

        * **parameters** (List[MethodParameter]) - Параметры метода. Необязательное поле.

          * **MethodParameter** - Включает в себя:

            * **attributes** (dict) - Атрибуты узла. Необязательное поле.

                * **cn** (str) - имя тега. Необязательный атрибут.
                * **description** (str) - описание экземпляра. Необязательный атрибут.
                * **prsJsonConfigString** (str) - Строка содержит, в случае необходимости,
                    конфигурацию узла. Интерпретируется сервисом, управляющим сущностью,
                    которой принадлежит экземпляр. Необязательный аттрибут
                * **prsActive** (bool) - Определяет, активен ли экземпляр. Необязательный атрибут.
                * **prsDefault** (bool) - Если = ``True``, то данный экземпляр. Необязательный атрибут.
                    считаеться узлом по умолчанию в списке равноправных узлов данного уровня иерархии.
                    Необязательный атрибут.
                * **prsIndex** (int) - Если у узлов одного уровня иерархии проставлены индексы, то
                    перед отдачей клиенту списка экземпляров они сортируются соответственно  их индексам. Необязательный атрибут.


    **Ответ:**

        * **id** (uuid) - id созданного тега
        * **detail** (str) - пояснения к ошибке

    """
    res = await app.create(payload)
    await error_handler.handle_error(res)
    return res

@router.get("/", response_model=svc.NodeReadResult | None, status_code=200)
async def read(q: str | None = None, payload: MethodRead | None = None, error_handler: svc.ErrorHandler = Depends()):
    res = await app.api_get_read(MethodRead, q, payload)
    await error_handler.handle_error(res)
    return res

@router.put("/", status_code=202)
async def update(payload: MethodUpdate, error_handler: svc.ErrorHandler = Depends()):
    res = await app.update(payload)
    await error_handler.handle_error(res)
    return res

@router.delete("/", status_code=202)
async def delete(payload: svc.NodeDelete, error_handler: svc.ErrorHandler = Depends()):
    res = await app.delete(payload)
    await error_handler.handle_error(res)
    return res

app.include_router(router, tags=["methods"])
