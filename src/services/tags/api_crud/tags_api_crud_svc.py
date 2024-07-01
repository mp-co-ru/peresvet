"""
Модуль содержит классы, описывающие входные данные для команд CRUD для тегов
и класс сервиса ``tags_api_crud_svc``\.
"""
import json
import sys
from uuid import UUID
from typing import Any, List
from pydantic import Field, validator

from fastapi import APIRouter, Depends

sys.path.append(".")

from src.common import api_crud_svc as svc
from src.services.tags.api_crud.tags_api_crud_settings import TagsAPICRUDSettings

class TagCreateAttributes(svc.NodeAttributes):
    prsArchive: bool = Field(
        True,
        title="Флаг архивирования начений тега.",
        description=(
            "Если = True, то значения тега записываются в базу данных, "
            "иначе хранится только текущее значение тега. **Не используется**."
        )
    )
    prsCompress: bool = Field(
        True,
        title="Флаг сжатия значений тега.",
        description=(
            "Если = True, значения тега будут проходить через алгоритм "
            "сжатия данных (в соответствии с параметром ``prsMaxLineDev``\). "
            "**Не используется**."
        )
    )
    prsMaxLineDev: float = Field(
        0,
        title="Параметр сжатия значений тега.",
        description="Алгоритм сжатия работает на стороне сервера"
    )
    prsStep: bool = Field(
        False,
        title="Флаг `ступенчатого тега`."
    )
    prsUpdate: bool = Field(
        True,
        title="Флаг обновления значений тега.",
        description=(
            "Если = True, то если новое значение тега приходит с меткой "
            "времени, на которую значение тега уже есть, то новое значение "
            "тега заменит старое. Иначе в хранилище будет несколько "
            "значений тега на одну метку времени."
        )
    )
    prsValueTypeCode: int = Field(
        1,
        title="Тип значений тега.",
        description=(
            "0 - целое, 1 - вещественное, 2 - строковое, 3 - дискретное, "
            "4 - json"
        )
    )
    prsDefaultValue: Any | None = Field(
        None,
        title="Значение тега по умолчанию.",
        description=(
            "Если присутствует, то указанное значение записывается "
            "в хранилище при создании тега с меткой времени на момент создания."
        )
    )
    prsMeasureUnits: str | None = Field(
        None,
        title="Единицы измерения тега."
    )

class TagCreate(svc.NodeCreate):
    attributes: TagCreateAttributes = Field({}, title="Атрибуты узла")
    validate_id = validator('parentId', allow_reuse=True)(svc.valid_uuid)

class TagRead(svc.NodeRead):
    pass

class TagUpdate(svc.NodeUpdate):
    validate_id = validator('parentId', 'id', allow_reuse=True)(svc.valid_uuid)

class TagsAPICRUD(svc.APICRUDSvc):
    """Сервис работы с тегами в иерархии.

    Подписывается на очередь ``tags_api_crud`` обменника ``tags_api_crud``\,
    в которую публикует сообщения сервис ``tags_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    _outgoing_commands = {
        "create": "tags.create",
        "read": "tags.read",
        "update": "tags.update",
        "delete": "tags.delete"
    }

    def __init__(self, settings: TagsAPICRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def create(self, payload: TagCreate) -> dict:
        return await super().create(payload=payload)

    async def read(self, payload: TagRead) -> dict:
        return await super().read(payload=payload)

    async def update(self, payload: TagUpdate) -> dict:
        return await super().update(payload=payload)

settings = TagsAPICRUDSettings()

app = TagsAPICRUD(settings=settings, title="`TagsAPICRUD` service")

router = APIRouter(prefix=f"{settings.api_version}/tags")

error_handler = svc.ErrorHandler()

@router.post("/", response_model=svc.NodeCreateResult, status_code=201)
async def create(payload: TagCreate, error_handler: svc.ErrorHandler = Depends()):
    """
    Метод добавляет тег в иерархию.

    **Request**:

        .. http:example::
            :request: ../../../../docs/source/samples/tags/addTagIn.txt
            :response: ../../../../docs/source/samples/tags/addTagOut.txt

        * **attributes** (dict) - словарь с параметрами для создания тега.

          * **cn** (str) - имя тега; Необязательный атрибут;
          * **description** (str) - описание экземпляра. Необязательный атрибут;
          * **prsJsonConfigString** (str) - Строка содержит, в случае необходимости,
            конфигурацию узла. Интерпретируется сервисом, управляющим сущностью,
            которой принадлежит экземпляр. Необязательный аттрибут
          * **prsActive** (bool) - Определяет, активен ли экземпляр. Необязательный атрибут;
          * **prsDefault** (bool) - Если = ``True``, то данный экземпляр. Необязательный атрибут;
            считается узлом по умолчанию в списке равноправных узлов данного уровня иерархии.
            Необязательный атрибут.
          * **prsIndex** (int) - Если у узлов одного уровня иерархии проставлены индексы, то
            перед отдачей клиенту списка экземпляров они сортируются
            в соответствии с их индексами. Необязательный атрибут
          * **prsArchive** (bool) - Флаг архивирования начений тега. Необязательный аттрибут
          * **prsCompress** (bool) - Флаг сжатия значений тега. Необязательный атрибут;
            Если не указан, то поиск ведётся от главного узла иерархии. Необязательный атрибут;
          * **prsMaxLineDev** (float) - Параметр сжатия значений тега. Необязательный атрибут;
          * **prsStep** (bool) - Флаг `ступенчатого тега`. Необязательный атрибут;
          * **prsUpdate** (bool) - Флаг обновления значений тега. Необязательный атрибут;
          * **prsValueTypeCode** (int) - Тип значений тега. Необязательный атрибут;
          * **prsDefaultValue** (Any) - Значение тега по умолчанию. Необязательный атрибут;
          * **prsMeasureUnits** (str) - Единицы измерения тега. Необязательный атрибут;


    **Response**:

        * **id** (uuid) - id созданного тега
        * **detail** (str) - пояснения к ошибке

    """
    res = await app.create(payload)
    await error_handler.handle_error(res)
    return res

@router.get("/", response_model=svc.NodeReadResult | None, status_code=200)
async def read(q: str | None = None, payload: TagRead | None = None, error_handler: svc.ErrorHandler = Depends()):
    """
    Метод чтения тега в иерархии.

    **Request**:

        .. http:example::
            :request: ../../../../docs/source/samples/tags/getTagIn.txt
            :response: ../../../../docs/source/samples/tags/getTagOut.txt

        * **id** (str | list(str)) - идентификатор тега, который мы хотим прочитать
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
          формируется фильтр для поиска. Необязательный аттрибут.


    **Response**:

        * **data** (list) - данные прочитанного тега/тегов. Если ничего не найденно -
          пустой лист.
        * **detail** (list) - Детали ошибки.

    """
    res = await app.api_get_read(TagRead, q, payload)
    await error_handler.handle_error(res)
    return res

@router.put("/", status_code=202)
async def update(payload: TagUpdate, error_handler: svc.ErrorHandler = Depends()):
    """
    Метод обновления тега в иерархии.

    **Request**:

        .. http:example::
            :request: ../../../../docs/source/samples/tags/putTagIn.txt
            :response: ../../../../docs/source/samples/tags/putTagOut.txt

        * **id** (str) - Идентификатор изменяемого узла.
        * **attributes** (dict) - словарь с параметрами для обновления тега.

          * **cn** (str) - имя тега; Необязательный атрибут;
          * **description** (str) - описание экземпляра. Необязательный атрибут;
          * **prsJsonConfigString** (str) - Строка содержит, в случае необходимости,
            конфигурацию узла. Интерпретируется сервисом, управляющим сущностью,
            которой принадлежит экземпляр. Необязательный аттрибут
          * **prsActive** (bool) - Определяет, активен ли экземпляр. Применяется,
            к примеру, для временного 'выключения' экземпляра на время, пока он ещё
            "недонастроен.
          * **prsDefault** (bool) - "Если = ``True``\, то данный экземпляр считается
            узлом по умолчанию в списке равноправных узлов данного уровня иерархии.
          * **prsEntityTypeCode** (int) - Атрибут используется для определения типа.
            К примеру, хранилища данных могут быть разных типов.
          * **prsIndex** (int) - Если у узлов одного уровня иерархии проставлены
            индексы, то перед отдачей клиенту списка экземпляров они сортируются
            в соответствии с их индексами.


    **Response**:

        * {} - пустой словарь в случае успешного запроса.
        * **detail** (list) - Детали ошибки.

    """
    res = await app.update(payload)
    await error_handler.handle_error(res)
    return res

@router.delete("/", status_code=202)
async def delete(payload: svc.NodeDelete, error_handler: svc.ErrorHandler = Depends()):
    """
    Метод удаления тега в иерархии.

    **Request**:

        .. http:example::
            :request: ../../../../docs/source/samples/tags/deleteTagIn.txt
            :response: ../../../../docs/source/samples/tags/deleteTagOut.txt

        * **id** (str | list[str]) - Идентификатор/ы удаляемого узла.


    **Response**:

        * null - в случае успешного запроса.
        * **detail** (list) - Детали ошибки.

    """
    res = await app.delete(payload)
    await error_handler.handle_error(res)
    return res

app.include_router(router, tags=["tags"])
