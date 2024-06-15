"""
Модуль содержит классы, описывающие входные данные для команд CRUD для тегов
и класс сервиса ``alerts_api_crud_svc``.
"""
import sys
from uuid import UUID
from typing import Any, List
from pydantic import Field
from fastapi import APIRouter, Depends

sys.path.append(".")

from src.common import api_crud_svc as svc
from src.services.alerts.api_crud.alerts_api_crud_settings import AlertsAPICRUDSettings

class AlertCreateAttributes(svc.NodeAttributes):
    """При создании тревоги атрибут ``prsJsonConfigString`` имеет формат

    .. code:: python

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

    Подписывается на очередь ``tags_api_crud`` обменника ``tags_api_crud``\,
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

router = APIRouter(prefix=f"{settings.api_version}/alerts")

error_handler = svc.ErrorHandler()

@router.post("/", response_model=svc.NodeCreateResult, status_code=201)
async def create(payload: AlertCreate, error_handler: svc.ErrorHandler = Depends()):
    """
    Метод добавляет ссылку (alias) на узел в иерархии.

    .. http:example:: python-requests
       :request: ../../../../docs/source/samples/alerts/addAliasIn.txt
       :response: ../../../../docs/source/samples/alerts/addAliasOut.txt

    **Request**:

        * **parentId** (str) - идентификатор узла, в который нужно добавить ссылку,
        * **attributes** (dict) -

          * **cn** (str) - имя сслыки; необязательный атрибут;
          * **aliasedObjectName** (str) - идентификатор объекта,
            на который создается ссылка

    **Response**:

        * **error** (dict) - объект, содержащий информацию об ошибке,
        * **id** (str) - идентификатор созданной ссылки
        * **uuid** (str) - идентификатор созданной ссылки (uuid)

    .. note::
        Если в запросе переданы атрибуты, не описанные в документации,
        они не будут обработаны функцией. Ошибка при этом возникать не будет.
    """

    res = await app.create(payload)
    await error_handler.handle_error(res)
    return res

@router.get("/", response_model=svc.NodeReadResult | None, status_code=200)
async def read(q: str | None = None, payload: AlertRead | None = None, error_handler: svc.ErrorHandler = Depends()):
    res = await app.api_get_read(AlertRead, q, payload)
    await error_handler.handle_error(res)
    return res

@router.put("/", status_code=202)
async def update(payload: AlertUpdate, error_handler: svc.ErrorHandler = Depends()):
    res = await app.update(payload)
    await error_handler.handle_error(res)
    return res

@router.delete("/", status_code=202)
async def delete(payload: svc.NodeDelete, error_handler: svc.ErrorHandler = Depends()):
    res = await app.delete(payload)
    await error_handler.handle_error(res)
    return res

app.include_router(router, tags=["alerts"])
