"""
Модуль содержит классы, описывающие входные данные для команд CRUD для коннекторов
и класс сервиса ``connectors_api_crud_svc``\.
"""
import sys
from pydantic import BaseModel, Field, validator, ConfigDict

from fastapi import APIRouter, Depends

sys.path.append(".")

from src.common import api_crud_svc as svc
from src.services.connectors.api_crud.connectors_api_crud_settings import ConnectorsAPICRUDSettings

class LinkTagAttributes(BaseModel):
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

    cn: str | None = Field(None, title="Имя привязки")
    prsJsonConfigString: dict = Field(
        title="Параметры подключение к источнику данных.",
        description=(
            "Json, хранящий ключи, которые указывают коннектору, как "
            "получать значения тега из источника данных. "
            "Формат словаря зависит от конкретного коннектора."
        )
    )
    description: str | None = Field(None, title="Пояснение")
    prsValueScale: int = Field(
        1,
        title=(
            "Коэффициент, на который умножается значение тега коннектором "
            "перед отправкой в платформу."
        )
    )
    prsMaxDev: int = Field(
        0,
        title="Величина значащего отклонения.",
        description="Используется коннекторами для снятия `дребезга` значений."
    )

    objectClass: str = Field("prsConnectorTagData", title="Класс объекта")

class LinkTag(BaseModel):
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

    tagId: str = Field(title="Идентификатор привязываемого тега")
    attributes: LinkTagAttributes = Field(title="Атрибуты тега")


class ConnectorAttributes(svc.NodeAttributes):
    prsJsonConfigString: dict = Field(
        title="Способ подключения к источнику данных",
        description=(
            "Json, содержащий информацию о том, как коннектор должен "
            "подключаться к источнику данных. Формат зависит от "
            "конкретного коннектора."
        )
    )

class ConnectorCreate(svc.NodeCreate):
    attributes: ConnectorAttributes = Field(title="Атрибуты коннектора")
    linkTags: list[LinkTag] = Field(
        [],
        title="Список добавленных тегов для коннектора"
    )

class ConnectorRead(svc.NodeRead):
    getLinkedTags: bool = Field(
        False,
        title="Флаг возврата присоединённых тегов"
    )

class OneConnectorInReadResult(svc.OneNodeInReadResult):
    linkedTags: list[LinkTag] = Field(
        None,
        title="Список привязанных к коннектору тегов"
    )

class ConnectorReadResult(svc.NodeReadResult):
    data: list[OneConnectorInReadResult] = Field(
        title="Список коннекторов"
    )

class ConnectorUpdate(ConnectorCreate):
    id: str = Field(title="Идентификатор изменяемого коннектора.",
                    description="Должен быть в формате GUID.")

    attributes: ConnectorAttributes = Field(None, title="Атрибуты коннектора")

    unlinkTags: list[str] = Field(
        [],
        title="Список отсоединенных тегов для коннектора"
    )

    validate_id = validator('id', allow_reuse=True)(svc.valid_uuid)

class ConnectorsAPICRUD(svc.APICRUDSvc):
    """Сервис работы с коннекторами в иерархии.

    Подписывается на очередь ``connectors_api_crud`` обменника ``connectors_api_crud``\,
    в которую публикует сообщения сервис ``connectors_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """
    _outgoing_commands = {
        "create": "connectors.create",
        "read": "connectors.read",
        "update": "connectors.update",
        "delete": "connectors.delete"
    }

    def __init__(self, settings: ConnectorsAPICRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def create(self, payload: ConnectorCreate) -> dict:
        return await super().create(payload=payload)

    async def read(self, payload: ConnectorRead) -> dict:
        return await super().read(payload=payload)

    async def update(self, payload: ConnectorUpdate) -> dict:
        return await super().update(payload=payload)

settings = ConnectorsAPICRUDSettings()

app = ConnectorsAPICRUD(settings=settings, title="`ConnectorsAPICRUD` service")

router = APIRouter(prefix=f"{settings.api_version}/connectors")

error_handler = svc.ErrorHandler()

@router.post("/", response_model=svc.NodeCreateResult, status_code=201)
async def create(payload: ConnectorCreate, error_handler: svc.ErrorHandler = Depends()):
    """
    Метод добавления коннектора в иерархию.

    **Request**:

        .. http:example::
            :request: ../../../../docs/source/samples/connectors/addConnectorIn.txt
            :response: ../../../../docs/source/samples/connectors/addConnectorOut.txt

        * **attributes** (dict) - словарь с параметрами для создания коннектора.
          Обязательный параметр.

          * **prsJsonConfigString** (str) - Способ подключения к источнику данных.
            Обязательный атрибут.
          * **cn** (str) - имя коннектора; Необязательный атрибут;
          * **description** (str) - описание коннектора. Необязательный атрибут;
          * **prsActive** (bool) - Определяет, активен ли экземпляр. Необязательный атрибут;
          * **prsDefault** (bool) - Если = ``True``, то данный экземпляр. Необязательный атрибут;
            считается узлом по умолчанию в списке равноправных узлов данного уровня иерархии.
            Необязательный атрибут.
          * **prsIndex** (int) - Если у узлов одного уровня иерархии проставлены индексы, то
            перед отдачей клиенту списка экземпляров они сортируются
            в соответствии с их индексами. Необязательный атрибут

        * **linkTags** (list[LinkTag]) - список тегов к которым прикреплен
          указанный коннектор; Обязательный атрибут;

          * **tagId** (str) - id прилинкованного тега. Обязательный атрибут;
          * **attributes** (dict) - словарь с параметрами для прилинкованного тега.
            Обязательный атрибут;

            * **cn** (str) - словарь с параметрами для прилинкованного тега.
              Необязательный атрибут.
            * **prsJsonConfigString** (dict) - Параметры подключение к источнику данных.
              Обязательный атрибут.
            * **description** (str) - Пояснение. Необязательный атрибут.
            * **prsValueScale** (int) - Коэффициент, на который умножается значение
              тега коннектором перед отправкой в платформу. Необязательный атрибут.
            * **prsMaxDev** (int) - Величина значащего отклонения. Необязательный атрибут.
            * **objectClass** (str) - Класс объекта. Необязательный атрибут.

    **Response**:

        * **id** (uuid) - id созданного коннектора
        * **detail** (str) - пояснения к ошибке

    """
    res = await app.create(payload)
    await error_handler.handle_error(res)
    return res

@router.get("/", response_model=ConnectorReadResult | None, status_code=200)
async def read(q: str | None = None, payload: ConnectorRead | None = None, error_handler: svc.ErrorHandler = Depends()):
    """
    Метод чтения коннектора из иерархии.

    **Request**:

        .. http:example::
            :request: ../../../../docs/source/samples/connectors/getConnectorIn.txt
            :response: ../../../../docs/source/samples/connectors/getConnectorOut.txt

        * **getLinkedTags** (bool) - Флаг возврата присоединённых тегов.
          Необязательный аттрибут.
        * **id** (str | list(str)) - идентификатор коннектора в формате uuid,
          который мы хотим прочитать. В случае отсутствия будут выведены все
          коннекторы или те, которые соответствуют фильтру. Необязательный аттрибут.
        * **attributes** (list[str]) - Список атрибутов, значения которых необходимо
          вернуть в ответе. По умолчанию - ['\*'], то есть все атрибуты (кроме системных).
          Необязательный аттрибут.
        * **base** (str) - Базовый узел для поиска. Если не указан, то поиск
          ведётся от главного узла иерархии. Необязательный аттрибут.
        * **deref** (bool) - Флаг разыменования ссылок. По умолчанию true.
          Необязательный аттрибут.
        * **scope** (int) - Масштаб поиска. По умолчанию 1. Необязательный аттрибут.\n
          0 - получение данных по указанному в ключе ``base`` узлу \n
          1 - поиск среди непосредственных потомков указанного в ``base`` узла\n
          2 - поиск по всему дереву, начиная с указанного в ``base`` узла.
        * **filter** (dict) - Словарь из атрибутов и их значений, из которых
          формируется фильтр для поиска. Необязательный аттрибут.


    **Response**:

        * **data** (list) - данные прочитанного коннектора/коннекторов. Если
          ничего не найденно - пустой лист.
        * **detail** (list) - Детали ошибки.

    """
    res = await app.api_get_read(ConnectorRead, q, payload)
    await error_handler.handle_error(res)
    return res

@router.put("/", status_code=202)
async def update(payload: ConnectorUpdate, error_handler: svc.ErrorHandler = Depends()):
    """
    Метод обновления коннектора из иерархии.

    **Request**:

        .. http:example::
            :request: ../../../../docs/source/samples/connectors/putConnectorIn.txt
            :response: ../../../../docs/source/samples/connectors/putConnectorOut.txt

        * **id** (bool) - Идентификатор изменяемого коннектора.
          Обязательный аттрибут.
        * **unlinkTags** (list[str]) - Список тегов для отсоединения от коннектора
          Необязательный аттрибут.
        * **attributes** (dict) - Атрибуты коннектора

            * **prsJsonConfigString** (dict) - Способ подключения к источнику данных. Необязательный аттрибут.
            * **cn** (str) - имя коннектора; Необязательный атрибут;
            * **description** (str) - описание коннектора. Необязательный атрибут;
            * **prsActive** (bool) - Параметр активности коннектора. Необязательный атрибут;
            * **prsDefault** (bool) - Если = ``True``\, то данный коннектор считается узлом по умолчанию в списке равноправных узлов данного уровня иерархии.
            * **prsEntityTypeCode** (int) - Атрибут используется для определения типа. К примеру, хранилища данных могут быть разных типов.
            * **prsIndex** (int) - Если у узлов одного уровня иерархии проставлены индексы, то перед отдачей клиенту списка экземпляров они сортируются в соответствии с их индексами.

    **Response**:

        * {} - Пустой словарь в случае успешного запроса.
        * **detail** (list) - Детали ошибки.

    """
    res = await app.update(payload)
    await error_handler.handle_error(res)
    return res

@router.delete("/", status_code=202)
async def delete(payload: ConnectorRead, error_handler: svc.ErrorHandler = Depends()):
    """
    Метод удаления коннектора в иерархии.

    **Request**:

        .. http:example::
            :request: ../../../../docs/source/samples/connectors/deleteConnectorIn.txt
            :response: ../../../../docs/source/samples/connectors/deleteConnectorOut.txt

        * **id** (str | list[str]) - Идентификатор/ы удаляемого узла.


    **Response**:

        * null - в случае успешного запроса.
        * **detail** (list) - Детали ошибки.

    """
    res = await app.delete(payload)
    await error_handler.handle_error(res)
    return res

app.include_router(router, tags=["connectors"])
