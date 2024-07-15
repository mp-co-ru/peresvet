"""
Модуль содержит примеры запросов и ответов на них, параметров которые могут входить в
запрос, в сервисе alerts.
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
    Метод добавляет тревогу в иерархию.

    **Request**:

        .. http:example::
            :request: ../../../../docs/source/samples/alerts/addAlertIn.txt
            :response: ../../../../docs/source/samples/alerts/addAlertOut.txt

        * **parentId** (str) - id тега к которому привязывается тревога. Обязательный атрибут
        * **attributes** (dict) - параметры создаваемой тревоги. Необязательное поле.

          * **cn** (str) - имя тревоги. Необязательный атрибут.
          * **description** (str) - описание экземпляра. Необязательный атрибут.
          * **prsJsonConfigString** (str) - Строка содержит, в случае необходимости,
            конфигурацию узла. Интерпретируется сервисом, управляющим сущностью,
            которой принадлежит экземпляр. Необязательный аттрибут
          * **prsActive** (bool) - Определяет, активен ли экземпляр. Необязательный атрибут
          * **prsDefault** (bool) - Если = ``True``, то данная тревога считаеться
            тревогой по умолчанию в списке равноправных узлов данного уровня иерархии.
            Необязательный атрибут.
          * **prsIndex** (int) - Если у узлов одного уровня иерархии проставлены индексы, то
            перед отдачей клиенту списка экземпляров они сортируются в соответствии
            с их индексами. Необязательный атрибут.

    **Response**:

        * **id** (str) - идентификатор созданной тревоги.
        * **detail** (str) - пояснение к возникшей ошибке.

    """

    res = await app.create(payload)
    await error_handler.handle_error(res)
    return res

@router.get("/", response_model=svc.NodeReadResult | None, status_code=200)
async def read(q: str | None = None, payload: AlertRead | None = None, error_handler: svc.ErrorHandler = Depends()):
    """
    Метод читает тревогу из иерархии.

    **Пример запроса в формате JSON.**

    .. http:example::
       :request: ../../../../docs/source/samples/alerts/getAlertsIn.txt
       :response: ../../../../docs/source/samples/alerts/getAlertsOut.txt

    **Пример query запроса.**

    .. http:example::
       :request: ../../../../docs/source/samples/alerts/getAlertsIn_query.txt
       :response: ../../../../docs/source/samples/alerts/getAlertsOut.txt

    **Параметры запроса.**

       * **id** (str | list(str)) - идентификатор тревоги, которую хотитим прочитать. Необязательный атрибут.
       * **base** (str) - Базовый узел для поиска. Обязательный атрибут.
       * **deref** (bool) - Флаг разыменования ссылок. По умолчанию true.
       * **scope** (int) - Масштаб поиска. По умолчанию 1.\n
         0 - получение данных по указанному в ключе ``base`` узлу \n
         1 - поиск среди непосредственных потомков указанного в ``base`` узла\n
         2 - поиск по всему дереву, начиная с указанного в ``base`` узла.
       * **filter** (dict) - Словарь из атрибутов и их значений, из которых
         формируется фильтр для поиска.
       * **attributes** (list[str]) - Список атрибутов, значения которых необходимо вернуть в ответе. По умолчанию - ['\*'], то есть все атрибуты (кроме системных).

    **Response**:

        * **data** (list) - найденные тревоги с их параметрами.
        * **detail** (str) - пояснение к возникшей ошибке.

    """

    res = await app.api_get_read(AlertRead, q, payload)
    await error_handler.handle_error(res)
    return res

@router.put("/", status_code=202)
async def update(payload: AlertUpdate, error_handler: svc.ErrorHandler = Depends()):
    """
    Метод обновляет тревогу в иерархии.

    **Request**:

        .. http:example::
            :request: ../../../../docs/source/samples/alerts/putAlertIn.txt
            :response: ../../../../docs/source/samples/alerts/putAlertOut.txt

        * **id** (str) - id тревоги для обновления. Обязательное поле.
        * **attributes** (dict) - словарь с параметрами для обновления.

          * **cn** (str) - имя тревоги. Необязательный атрибут.
          * **description** (str) - описание экземпляра. Необязательный атрибут.
          * **prsJsonConfigString** (str) - Строка содержит, в случае необходимости,
            конфигурацию узла. Интерпретируется сервисом, управляющим сущностью,
            которой принадлежит экземпляр. Необязательный атрибут.
          * **prsActive** (bool) - Определяет, активен ли экземпляр. Необязательный атрибут.
          * **prsDefault** (bool) - Если = ``True``, то данный экземпляр
            считается узлом по умолчанию в списке равноправных узлов данного уровня иерархии.
            Необязательный атрибут.
          * **prsIndex** (int) - Если у узлов одного уровня иерархии проставлены индексы, то
            перед отдачей клиенту списка экземпляров они сортируются
            в соответствии с их индексами. Необязательный атрибут

    **Response**:

        * {} - пустой словарь в случае успешного запроса.
        * **detail** (list) - список с поснениями к ошибке.

    """
    res = await app.update(payload)
    await error_handler.handle_error(res)
    return res

@router.delete("/", status_code=202)
async def delete(payload: svc.NodeDelete, error_handler: svc.ErrorHandler = Depends()):
    """
    Метод удаляет тревогу из иерархии.

    **Request**:

        .. http:example::
            :request: ../../../../docs/source/samples/alerts/deleteAlertIn.txt
            :response: ../../../../docs/source/samples/alerts/deleteAlertOut.txt

        * **id** (str) - id тревоги для удаления. Обязательное поле.

    **Response**:

        * null - в случае успешного запроса
        * **detail** (list) - список с поснениями к ошибке

    """
    res = await app.delete(payload)
    await error_handler.handle_error(res)
    return res

app.include_router(router, tags=["alerts"])
