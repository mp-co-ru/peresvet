"""
Модуль содержит примеры запросов и ответов на них, параметров которые могут входить в
запрос, в сервисе objects.
"""
import sys
from typing import List
from pydantic import Field
import json
from fastapi import APIRouter, Depends
#from fastapi.middleware.cors import CORSMiddleware

sys.path.append(".")

from src.common import api_crud_svc as svc
from src.services.objects.api_crud.objects_api_crud_settings import ObjectsAPICRUDSettings

class ObjectCreateAttributes(svc.NodeAttributes):
    pass

class ObjectCreate(svc.NodeCreate):
    attributes: ObjectCreateAttributes | None = Field({}, title="Атрибуты объекта")

    # validate_id = validator('parentId', 'dataStorageId', 'connectorId', allow_reuse=True)(svc.valid_uuid)

class ObjectRead(svc.NodeRead):
    pass

class OneObjectInReadResult(svc.OneNodeInReadResult):
    pass

class ObjectReadResult(svc.NodeReadResult):
    data: List[OneObjectInReadResult] = Field(title="Список объектов.")
    pass

class ObjectUpdate(svc.NodeUpdate):
    pass

class ObjectsAPICRUD(svc.APICRUDSvc):
    """Сервис работы с объектами в иерархии.

    Подписывается на очередь ``objects_api_crud`` обменника ``objects_api_crud``\,
    в которую публикует сообщения сервис ``objects_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: ObjectsAPICRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def _create(self, payload: ObjectCreate | None) -> dict:
        return await super()._create(payload=payload)

    async def _read(self, payload: ObjectRead) -> dict:
        return await super()._read(payload=payload)

    async def _update(self, payload: dict) -> dict:
        return await super()._update(payload=payload)

settings = ObjectsAPICRUDSettings()

app = ObjectsAPICRUD(settings=settings, title="`ObjectsAPICRUD` service")

router = APIRouter(prefix=f"{settings.api_version}/objects")

error_handler = svc.ErrorHandler()

@router.post("/", response_model=svc.NodeCreateResult, status_code=201)
async def create(payload: dict = None, error_handler: svc.ErrorHandler = Depends()):
    """
    Метод добавляет обьект в иерархию.

    **Запрос:**

        .. http:example::
            :request: ../../../../docs/source/samples/objects/addObjectIn.txt
            :response: ../../../../docs/source/samples/objects/addObjectOut.txt

        * **attributes** (dict) - словарь с параметрами для создания обьекта.

          * **cn** (str) - имя обьекта; Обязательный атрибут.
          * **description** (str) - описание обьекта. Необязательный атрибут.
          * **prsJsonConfigString** (str) - Строка содержит, в случае необходимости,
            конфигурацию узла. Интерпретируется сервисом, управляющим сущностью,
            которой принадлежит экземпляр. Необязательный аттрибут.
          * **prsActive** (bool) - Определяет, активен ли экземпляр. Необязательный атрибут.
          * **prsDefault** (bool) - Если = ``True``, то данный экземпляр. Необязательный атрибут.
            считается узлом по умолчанию в списке равноправных узлов данного уровня иерархии.
            Необязательный атрибут.
          * **prsIndex** (int) - Если у узлов одного уровня иерархии проставлены индексы, то
            перед отдачей клиенту списка экземпляров они сортируются
            в соответствии с их индексами. Необязательный атрибут.


    **Ответ:**

        * **id** (uuid) - id созданного обьекта
        * **detail** (str) - пояснения к ошибке

    """
    if payload is None:
        payload = {}
    
    try:
        s = json.dumps(payload)
        p = ObjectCreate.model_validate_json(s)
    except Exception as ex:
        res = {"error": {"code": 422, "message": f"Несоответствие входных данных: {ex}"}}
        app._logger.exception(res)
        await error_handler.handle_error(res)

    res = await app._create(p)
    await error_handler.handle_error(res)
    return res

@router.get("/", response_model=svc.NodeReadResult | None, status_code=200, response_model_exclude_none=True)
async def read(q: str | None = None, payload: ObjectRead | None = None, error_handler: svc.ErrorHandler = Depends()):
    """
    Метод чтения обьекта в иерархии.

    **Пример запроса в формате JSON.**

        .. http:example::
            :request: ../../../../docs/source/samples/objects/getObjectIn.txt
            :response: ../../../../docs/source/samples/objects/getObjectOut.txt

    **Пример query запроса.**

        .. http:example::
            :request: ../../../../docs/source/samples/objects/getObjectIn_query.txt
            :response: ../../../../docs/source/samples/objects/getObjectOut.txt

    **Параметры запроса:**

        * **id** (str | list(str)) - идентификатор объекта, который мы хотим прочитать
          Необязательный аттрибут.
        * **cn** (str) - имя объекта, который мы хотим прочитать
          Необязательный аттрибут.
        * **attributes** (list[str]) - Список атрибутов, значения которых необходимо
          вернуть в ответе. По умолчанию - ['\*'], то есть все атрибуты (кроме системных).
          Необязательный аттрибут.
        * **base** (str) - Базовый узел для поиска. Необязательный аттрибут.
          Если не указан, то поиск ведётся от главного узла иерархии.
        * **deref** (bool) - Флаг разыменования ссылок. По умолчанию true.
          Необязательный аттрибут.
        * **scope** (int) - Масштаб поиска. По умолчанию 1. Необязательный аттрибут.\n
          0 - получение данных по указанному в ключе ``base`` узлу \n
          1 - поиск среди непосредственных потомков указанного в ``base`` узла\n
          2 - поиск по всему дереву, начиная с указанного в ``base`` узла.
        * **filter** (dict) - Словарь из атрибутов и их значений, из которых
          формируется фильтр для поиска. Необязательный атрибут.


    **Ответ:**

        * **data** (list) - данные прочитанного тега/тегов. Если ничего не найденно -
          пустой лист.
        * **detail** (list) - Детали ошибки.

    """
    res = await app.api_get_read(ObjectRead, q, payload)
    await error_handler.handle_error(res)
    return res

@router.put("/", status_code=202)
async def update(payload: dict, error_handler: svc.ErrorHandler = Depends()):
    """
    Метод обновления обьекта в иерархии.

    **Запрос:**

        .. http:example::
            :request: ../../../../docs/source/samples/objects/putObjectIn.txt
            :response: ../../../../docs/source/samples/objects/putObjectOut.txt

        * **id** (str) - Идентификатор изменяемого узла.
        * **attributes** (dict) - словарь с параметрами для обновления объекта.

          * **cn** (str) - имя объекта. Необязательный атрибут.
          * **description** (str) - описание объекта. Необязательный атрибут.
          * **prsJsonConfigString** (str) - Строка содержит, в случае необходимости,
            конфигурацию узла. Интерпретируется сервисом, управляющим сущностью,
            которой принадлежит экземпляр. Необязательный аттрибут.
          * **prsActive** (bool) - Определяет, активен ли экземпляр. Применяется,
            к примеру, для временного 'выключения' экземпляра на время, пока он ещё
            не настроен окончательно. Необязательный аттрибут.
          * **prsDefault** (bool) - "Если = ``True``\, то данный экземпляр считается
            узлом по умолчанию в списке равноправных узлов данного уровня иерархии.
            Необязательный аттрибут.
          * **prsEntityTypeCode** (int) - Атрибут используется для определения типа.
            К примеру, хранилища данных могут быть разных типов. Необязательный аттрибут.
          * **prsIndex** (int) - Если у узлов одного уровня иерархии проставлены
            индексы, то перед отдачей клиенту списка экземпляров они сортируются
            в соответствии с их индексами. Необязательный аттрибут.


    **Ответ:**

        * {} - пустой словарь в случае успешного запроса.
        * **detail** (list) - детали ошибки.

    """
    try:
        ObjectUpdate.model_validate(payload)
    except Exception as ex:
        res = {"error": {"code": 422, "message": f"Несоответствие входных данных: {ex}"}}
        app._logger.exception(res)
        await error_handler.handle_error(res)

    res = await app._update(payload)
    await error_handler.handle_error(res)
    return res

@router.delete("/", status_code=202)
async def delete(payload: ObjectRead, error_handler: svc.ErrorHandler = Depends()):
    """
    Метод удаления объекта в иерархии.

    **Запрос:**

        .. http:example::
            :request: ../../../../docs/source/samples/objects/deleteObjectIn.txt
            :response: ../../../../docs/source/samples/objects/deleteObjectOut.txt

        * **id** (str | list[str]) - Идентификатор/ы удаляемого объекта.


    **Ответ:**

        * null - в случае успешного запроса.
        * **detail** (list) - детали ошибки.

    """
    res = await app._delete(payload)
    await error_handler.handle_error(res)
    return res

app.include_router(router, tags=["objects"])
