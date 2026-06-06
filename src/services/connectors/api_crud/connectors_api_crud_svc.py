"""
Модуль содержит примеры запросов и ответов на них, параметров которые могут входить в
запрос, в сервисе connectors.
"""
import sys
import json
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict

from fastapi import APIRouter, Depends, Query

sys.path.append(".")

from src.common import api_crud_svc as svc
from src.services.connectors.api_crud.connectors_api_crud_settings import ConnectorsAPICRUDSettings

class ConfigStringForLinkedTag(BaseModel):
    source: dict = Field({},
        title="Способ получения данных тега от источника",
        description="Каждый тип коннектора определяет формат этого словаря."
    )
    maxDev: float = Field(0, title="Отклонение значения от предыдущей величины.",
        description=(
            "Коннектор отсылает данные в платформу для тега, если разница между вновь полученным "
            "значением и последним отосланным в платформу превышает указанное значение."
        )
    )
    JSONata: str | None = Field(None,
        title="Выражение на языке JSONata",
        description="Это выражение будет применено к прочитанным из источника данным."
    )
    frequency: float | None = Field(None,
        title="Частота сбора",
        description="Частота, с которой будут читаться данные тега из источника коннектором в случае."
    )
class LinkTagAttributes(BaseModel):
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

    cn: str | None = Field(None, title="Имя привязки")
    prsJsonConfigString: ConfigStringForLinkedTag = Field(
        title="Параметры подключение к источнику данных.",
        description=(
            "Json, хранящий ключи, которые указывают коннектору, как "
            "получать значения тега из источника данных. "
            "Формат словаря зависит от конкретного коннектора."
        )
    )
    description: str | None = Field(None, title="Пояснение")
    objectClass: str = Field("prsConnectorTagData", title="Класс объекта")

    @field_validator("prsJsonConfigString", mode="before")
    @classmethod
    def coerce_link_tag_prs_json(cls, v):
        if isinstance(v, ConfigStringForLinkedTag):
            return v
        if isinstance(v, dict):
            return v
        d = svc.coerce_prs_json_config_string_value(v)
        if d is None:
            d = {}
        return d

class LinkTag(BaseModel):
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

    tagId: str = Field(title="Идентификатор привязываемого тега")
    attributes: LinkTagAttributes = Field(title="Атрибуты тега")
class ConnectorAttributes(svc.NodeAttributes):
    prsJsonConfigString: dict | None = Field({},
        title="Способ подключения к источнику данных",
        description=(
            "Json, содержащий информацию о том, как коннектор должен "
            "подключаться к источнику данных. Формат зависит от "
            "конкретного коннектора."
        )
    )

    @field_validator("prsJsonConfigString", mode="before")
    @classmethod
    def coerce_prs_json_config_string(cls, v):
        v = svc.coerce_prs_json_config_string_value(v)
        if v is None:
            return {}
        return v

class ConnectorCreate(svc.NodeCreate):
    attributes: ConnectorAttributes | None = Field(None, title="Атрибуты коннектора")
    linkedTags: list[LinkTag] = Field(
        [],
        title="Список добавленных тегов для коннектора"
    )

class ConnectorCopy(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    sourceId: str = Field(title="Id копируемого коннектора")
    copyLinkedTags: bool = Field(
        False,
        title="Копировать привязки тегов исходного коннектора",
    )
    attributes: dict | None = Field(
        None,
        title="Необязательные атрибуты копии (например cn).",
    )

    @field_validator("sourceId")
    @classmethod
    def validate_source_id(cls, v: str) -> str:
        return svc.valid_uuid(v)

    @model_validator(mode="before")
    @classmethod
    def _coerce_prs_json_strings_in_body(cls, data):
        """До разбора полей: строковые prsJsonConfigString (textarea) -> dict по всему телу."""
        if isinstance(data, dict):
            svc.coerce_prs_json_strings_in_mapping_tree(data)
        return data

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

    attributes: ConnectorAttributes | None = Field(None, title="Атрибуты коннектора")

    unlinkTags: list[str] = Field(
        [],
        title="Список отсоединенных тегов для коннектора"
    )

    @field_validator("id")
    @classmethod
    def validate_id(cls, v):
        return svc.valid_uuid(v)

class ConnectorsAPICRUD(svc.APICRUDSvc):
    """Сервис работы с коннекторами в иерархии.

    Подписывается на очередь ``connectors_api_crud`` обменника ``connectors_api_crud``,
    в которую публикует сообщения сервис ``connectors_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """
    def __init__(self, settings: ConnectorsAPICRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def _create(self, payload: ConnectorCreate, routing_key: str | None = None) -> dict | bool | None:
        return await super()._create(payload=payload)

    async def _read(self, payload: ConnectorRead, routing_key: str | None = None) -> dict | bool | None:
        return await super()._read(payload=payload)

    async def _update(self, payload: dict, routing_key: str | None = None) -> dict | bool | None:
        return await super()._update(payload=payload)

settings = ConnectorsAPICRUDSettings()

app = ConnectorsAPICRUD(settings=settings, title="`ConnectorsAPICRUD` service")

router = APIRouter(prefix=f"{settings.api_version}/connectors")

error_handler = svc.ErrorHandler()

@router.post("/", response_model=svc.NodeCreateResult, status_code=201)
async def create(payload: dict | None = None, error_handler: svc.ErrorHandler = Depends()):
    """
    Метод добавления коннектора в иерархию.

    **Запрос:**

        .. http:example::
            :request: ../../../../docs/source/samples/connectors/addConnectorIn.txt
            :response: ../../../../docs/source/samples/connectors/addConnectorOut.txt

        * **attributes** (dict) - словарь с параметрами для создания коннектора.
          Обязательный параметр.

          * **prsJsonConfigString** (str) - Способ подключения к источнику данных.
            Обязательный атрибут.
          * **cn** (str) - имя коннектора. Необязательный атрибут.
          * **description** (str) - описание коннектора. Необязательный атрибут.
          * **prsActive** (bool) - Определяет, активен ли экземпляр. Необязательный атрибут.
          * **prsDefault** (bool) - Если = ``True``, то данный экземпляр. Необязательный атрибут.
            считается узлом по умолчанию в списке равноправных узлов данного уровня иерархии.
            Необязательный атрибут.
          * **prsIndex** (int) - Если у узлов одного уровня иерархии проставлены индексы, то
            перед отдачей клиенту списка экземпляров они сортируются
            в соответствии с их индексами. Необязательный атрибут.

        * **linkedTags** (list[LinkTag]) - список тегов к которым прикреплен
          указанный коннектор. Обязательный атрибут.

          * **tagId** (str) - id прикрепляемого тега. Обязательный атрибут.
          * **attributes** (dict) - словарь с параметрами для прилинкованного тега.
            Обязательный атрибут.

            * **cn** (str) - словарь с параметрами для прикрепляемого тега.
              Необязательный атрибут.
            * **prsJsonConfigString** (dict) - Параметры подключение к источнику данных.
              Обязательный атрибут.
            * **description** (str) - Пояснение. Необязательный атрибут.
            * **objectClass** (str) - Класс объекта. Необязательный атрибут.

    **Ответ:**

        * **id** (uuid) - id созданного коннектора.
        * **detail** (str) - пояснения к ошибке.

    """
    if payload is None:
        payload = {}
    if payload.get("sourceId"):
        try:
            svc.coerce_prs_json_strings_in_mapping_tree(payload.get("attributes") or {})
            p_copy = ConnectorCopy.model_validate(payload)
        except Exception as ex:
            res = {"error": {"code": 422, "message": f"Несоответствие входных данных: {ex}"}}
            app._logger.exception(res)
            await error_handler.handle_error(res)
        res = await app._post_message(
            mes=p_copy.model_dump(exclude_none=True),
            reply=True,
            routing_key="prsConnector.api_crud.copy",
        )
        await error_handler.handle_error(res)
        return res

    try:
        s = json.dumps(payload)
        p = ConnectorCreate.model_validate_json(s)
    except Exception as ex:
        res = {"error": {"code": 422, "message": f"Несоответствие входных данных: {ex}"}}
        app._logger.exception(res)
        await error_handler.handle_error(res)

    res = await app._create(p)
    await error_handler.handle_error(res)
    return res

@router.get("/", response_model=ConnectorReadResult | None, status_code=200, response_model_exclude_none=True)
async def read(
    # отдельные query-параметры (основной путь)
    id: list[str] | None = Query(None),
    base: str | None = None,
    deref: bool = True,
    scope: int = 1,
    hierarchy: bool = False,
    getParent: bool = False,
    attributes: list[str] | None = Query(None),
    filter: str | None = None,
    getLinkedTags: bool = False,
    # fallback
    q: str | None = None,
    payload: ConnectorRead | None = None,
    error_handler: svc.ErrorHandler = Depends(),
):
    """
    Метод чтения коннектора из иерархии.

    **Пример запроса в формате JSON.**

    .. http:example::
       :request: ../../../../docs/source/samples/connectors/getConnectorIn.txt
       :response: ../../../../docs/source/samples/connectors/getConnectorOut.txt

    **Пример query запроса.**

    .. http:example::
       :request: ../../../../docs/source/samples/connectors/getConnectorIn_query.txt
       :response: ../../../../docs/source/samples/connectors/getConnectorOut.txt

    **Параметры запроса:**

       * **getLinkedTags** (bool) - Флаг возврата присоединённых тегов.
         Необязательный аттрибут.
       * **id** (str | list(str)) - идентификатор коннектора в формате uuid,
         который мы хотим прочитать. В случае отсутствия будут выведены все
         коннекторы или те, которые соответствуют фильтру. Необязательный аттрибут.
       * **attributes** (list[str]) - Список атрибутов, значения которых необходимо
         вернуть в ответе. По умолчанию - ['.'], то есть все атрибуты (кроме системных).
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


    **Ответ:**

        * **data** (list) - данные прочитанного коннектора/коннекторов. Если
          ничего не найденно - пустой лист.
        * **detail** (list) - Детали ошибки.

    """
    if q is not None or payload is not None:
        res = await app.api_get_read(ConnectorRead, q, payload)
    else:
        body: dict = {
            "deref": deref,
            "scope": scope,
            "hierarchy": hierarchy,
            "getParent": getParent,
            "getLinkedTags": getLinkedTags,
        }
        if id is not None:
            body["id"] = id
        if base is not None:
            body["base"] = base
        if attributes is not None:
            body["attributes"] = attributes
        if filter is not None:
            body["filter"] = json.loads(filter)
        p = ConnectorRead.model_validate(body)
        res = await app._read(p)
    await error_handler.handle_error(res)
    return res

@router.put("/", status_code=202)
async def update(payload: dict, error_handler: svc.ErrorHandler = Depends()):
    """
    Метод обновления коннектора из иерархии.

    **Запрос:**

        .. http:example::
            :request: ../../../../docs/source/samples/connectors/putConnectorIn.txt
            :response: ../../../../docs/source/samples/connectors/putConnectorOut.txt

        * **id** (bool) - Идентификатор изменяемого коннектора.
          Обязательный аттрибут.
        * **linkedTags** (list[LinkTag]) - список тегов, привязанных к указанному коннектору. Необязательный атрибут.
        * **unlinkTags** (list[str]) - Список тегов для отсоединения от коннектора.
          Необязательный аттрибут.
        * **attributes** (dict) - Атрибуты коннектора

            * **prsJsonConfigString** (dict) - Способ подключения к источнику данных. Необязательный аттрибут.
            * **cn** (str) - имя коннектора. Необязательный атрибут
            * **description** (str) - описание коннектора. Необязательный атрибут.
            * **prsActive** (bool) - Параметр активности коннектора. Необязательный атрибут.
            * **prsDefault** (bool) - Если = ``True``, то данный коннектор считается узлом по умолчанию в списке равноправных узлов данного уровня иерархии.
            * **prsEntityTypeCode** (int) - Атрибут используется для определения типа. К примеру, хранилища данных могут быть разных типов.
            * **prsIndex** (int) - Если у узлов одного уровня иерархии проставлены индексы, то перед отдачей клиенту списка экземпляров они сортируются в соответствии с их индексами.

    **Ответ:**

        * {} - Пустой словарь в случае успешного запроса.
        * **detail** (list) - Детали ошибки.

    """
    try:
        ConnectorUpdate.model_validate(payload)
    except Exception as ex:
        res = {"error": {"code": 422, "message": f"Несоответствие входных данных: {ex}"}}
        app._logger.exception(res)
        await error_handler.handle_error(res)

    res = await app._update(payload=payload)
    await error_handler.handle_error(res)
    return res

@router.delete("/", status_code=202)
async def delete(payload: ConnectorRead, error_handler: svc.ErrorHandler = Depends()):
    """
    Метод удаления коннектора в иерархии.

    **Запрос:**

        .. http:example::
            :request: ../../../../docs/source/samples/connectors/deleteConnectorIn.txt
            :response: ../../../../docs/source/samples/connectors/deleteConnectorOut.txt

        * **id** (str | list[str]) - Идентификатор/ы удаляемого узла.


    **Ответ:**

        * null - в случае успешного запроса.
        * **detail** (list) - Детали ошибки.

    """
    res = await app._delete(payload)
    await error_handler.handle_error(res)
    return res

app.include_router(router, tags=["connectors"])
