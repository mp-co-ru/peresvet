"""
Модуль содержит классы, описывающие входные данные для команд CRUD для тегов
и класс сервиса ``tags_api_crud_svc``.
"""
import sys
from uuid import UUID
from typing import Any, List
from pydantic import Field
from fastapi import APIRouter

sys.path.append(".")

from src.common import api_crud_svc as svc
from src.services.alerts.api_crud.alerts_api_crud_settings import AlertsAPICRUDSettings

class AlertCreateAttributes(svc.NodeAttributes):
    """При создании тревоги атрибут ``prsJsonConfigString`` имеет формат
    {
        # "тревожное" значение тега
        "value": ...
        # способ сравнения значения тега с "тревожным":
        # если high = true, то тревога возникает, если значение тега >= value
        # иначе - значение тега < value
        "high": true
        # флаг автоквитирования
        "autoAck": true
    }

    Args:
        svc (_type_): _description_
    """
    pass

class AlertCreate(svc.NodeCreate):
    attributes: AlertCreateAttributes = Field({}, title="Атрибуты тревоги")

class AlertRead(svc.NodeRead):
    pass

class AlertUpdate(svc.NodeUpdate):
    pass

class AlertsAPICRUD(svc.APICRUDSvc):
    """Сервис работы с тегами в иерархии.

    Подписывается на очередь ``tags_api_crud`` обменника ``tags_api_crud``,
    в которую публикует сообщения сервис ``tags_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    _outgoing_commands = {
        "create": "alerts.create",
        "read": "alerts.read",
        "update": "alerts.update",
        "delete": "alerts.delete"
    }

    def __init__(self, settings: AlertsAPICRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def create(self, payload: AlertCreate) -> dict:
        return await super().create(payload=payload)

    async def read(self, payload: AlertRead) -> dict:
        return await super().read(payload=payload)

    async def update(self, payload: AlertUpdate) -> dict:
        return await super().update(payload=payload)

settings = AlertsAPICRUDSettings()

app = AlertsAPICRUD(settings=settings, title="`AlertsAPICRUD` service")

router = APIRouter()

@router.post("/", response_model=svc.NodeCreateResult, status_code=201)
async def create(payload: AlertCreate):
    return await app.create(payload)

@router.get("/", response_model=svc.NodeReadResult, status_code=200)
async def read(payload: AlertRead):
    return await app.read(payload)

@router.put("/", status_code=202)
async def update(payload: AlertUpdate):
    await app.update(payload)

@router.delete("/", status_code=202)
async def delete(payload: svc.NodeDelete):
    await app.delete(payload)

app.include_router(router, prefix=f"{settings.api_version}/alerts", tags=["alerts"])
