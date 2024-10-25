"""
Модуль содержит примеры запросов и ответов на них, параметров которые могут входить в
запрос, в сервисе dataStorages.
"""
import sys
from pydantic import BaseModel, Field, validator, ConfigDict
from fastapi import APIRouter, Depends

sys.path.append(".")

from src.common import api_crud_svc as svc
from src.services.dataStorages.api_crud.dataStorages_api_crud_settings import DataStoragesAPICRUDSettings

class LinkTagOrAlertAttributes(BaseModel):
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

    cn: str = Field(title="Имя привязки")
    prsStore: dict | None = Field(None, title="Хранилище тега/тревоги")

class LinkTag(BaseModel):
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

    tagId: str = Field(title="Идентификатор привязываемого тега")
    attributes: LinkTagOrAlertAttributes = Field({})

class LinkAlert(BaseModel):
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

    alertId: str = Field(title="Идентификатор привязываемой тревоги")
    attributes: LinkTagOrAlertAttributes = Field({})

class DataStorageAttributes(svc.NodeAttributes):
    pass

class DataStorageCreate(svc.NodeCreate):
    attributes: DataStorageAttributes = Field(title="Атрибуты хранилища")
    linkTags: list[LinkTag] = Field([], title="Список привязываемых тегов")
    linkAlerts: list[LinkAlert] = Field([], title="Список привязываемых тревог")
    # unlinkTags: list[LinkTag] | None = Field([], title="Список id тегов.")

    @validator('attributes')
    @classmethod
    def ds_type_is_necessary(cls, v: DataStorageAttributes) -> DataStorageAttributes:
        # если не указан тип базы данных, то по умолчанию используется
        # PostgreSQL
        if v.prsEntityTypeCode is None:
            v.prsEntityTypeCode = 0

        return v

class  DataStorageRead(svc.NodeRead):
    getLinkedTags: bool = Field(
        False,
        title="Флаг возврата присоединённых тегов"
    )
    getLinkedAlerts: bool = Field(
        False,
        title="Флаг возврата присоединённых тревог"
    )

class OneDataStorageInReadResult(svc.OneNodeInReadResult):
    linkedTags: list[LinkTag] | None = Field(
        None,
        title="Список id присоединённых тегов."
    )
    linkedAlerts: list[LinkAlert] | None = Field(
        None,
        title="Список id присоединённых тревог."
    )

class DataStorageReadResult(svc.NodeReadResult):
    data: list[OneDataStorageInReadResult] = Field(title="Список хранилищ данных.")

class DataStorageUpdate(DataStorageCreate):
    id: str = Field(title="Идентификатор изменяемого узла.",
                    description="Должен быть в формате GUID.")

    attributes: DataStorageAttributes = Field(None, title="Атрибуты хранилища")

    unlinkTags: list[str] | None = Field(
        [],
        title="Список id тегов."
    )
    unlinkAlerts: list[str] | None = Field(
        [],
        title="Список id тревог."
    )

    validate_id = validator('id', allow_reuse=True)(svc.valid_uuid)

class DataStoragesAPICRUD(svc.APICRUDSvc):
    """Сервис работы с хранилищами данных в иерархии.

    Подписывается на очередь ``dataStorages_api_crud`` обменника ``dataStorages_api_crud``\,
    в которую публикует сообщения сервис ``dataStorages_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """
    def __init__(self, settings: DataStoragesAPICRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def _create(self, payload: DataStorageCreate) -> dict:
        return await super()._create(payload=payload)

    async def _read(self, payload: DataStorageRead) -> dict:
        return await super()._read(payload=payload)

    async def _update(self, payload: dict) -> dict:
        return await super()._update(payload=payload)

settings = DataStoragesAPICRUDSettings()

app = DataStoragesAPICRUD(settings=settings, title="`DataStoragesAPICRUD` service")

router = APIRouter(prefix=f"{settings.api_version}/dataStorages")

error_handler = svc.ErrorHandler()

@router.post("/", response_model=svc.NodeCreateResult, status_code=201)
async def create(payload: DataStorageCreate, error_handler: svc.ErrorHandler = Depends()):
    """
    Метод добавляет Хранилище данных в иерархию.

    **Запрос:**

        .. http:example::
            :request: ../../../../docs/source/samples/dataStorages/addDSIn.txt
            :response: ../../../../docs/source/samples/dataStorages/addDSOut.txt

        * **linkTags** (list[LinkTag]) - Список привязываемых тегов.

          * **LinkTag** - Привязываемый тег. Включает в себя:

            * **tagId** (str) - идентификатор привязываемого тега. Обязательный атрибут.
            * **attributes** - список параметров привязываемого тега.

              * **cn** (str) - Имя привязки. Обязательный атрибут.
              * **prsStore** (dict) - Хранилище тега. Необязательный атрибут.
              * **objectClass** (str) - Класс узла. Обязательный атрибут.

        * **linkAlerts** (list[LinkAlert]) - Список привязываемых тревог

          * **LinkAlert** - Привязываемая тревога. Включает в себя:

            * **alertId** (str) - Идентификатор привязываемой тревоги. Обязательный атрибут.
            * **attributes** - список параметров привязываемой тревоги. Включает в себя:

              * **cn** (str) - Имя привязки. Обязательный атрибут.
              * **prsStore** (dict) - Хранилище тревоги. Необязательный атрибут.
              * **objectClass** (str) - Класс узла. Обязательный атрибут.

        * **attributes** (dict) - Атрибуты хранилища

          * **cn** (str) - имя хранилища. Необязательный атрибут.
          * **description** (str) - описание хранилища. Необязательный атрибут.
          * **prsJsonConfigString** (str) - Строка содержит, в случае необходимости,
            конфигурацию узла. Интерпретируется сервисом, управляющим сущностью,
            которой принадлежит экземпляр. Необязательный аттрибут
          * **prsActive** (bool) - Определяет, активно ли хранилище. Необязательный атрибут.
          * **prsDefault** (bool) - Если = ``True``, то данный экземпляр. Необязательный атрибут.
            считается узлом по умолчанию в списке равноправных узлов данного уровня иерархии.
            Необязательный атрибут.
          * **prsIndex** (int) - Если у узлов одного уровня иерархии проставлены индексы, то
            перед отдачей клиенту списка экземпляров они сортируются
            в соответствии с их индексами. Необязательный атрибут.

    **Ответ:**

        * **id** (uuid) - id созданного тега
        * **detail** (str) - пояснения к ошибке

    """
    res = await app._create(payload)
    await error_handler.handle_error(res)
    return res

@router.get("/", response_model=DataStorageReadResult | None, status_code=200, response_model_exclude_none=True)
async def read(q: str | None = None, payload: DataStorageRead | None = None, error_handler: svc.ErrorHandler = Depends()):
    res = await app.api_get_read(DataStorageRead, q, payload)
    await error_handler.handle_error(res)
    return res

@router.put("/", status_code=202)
async def update(payload: dict, error_handler: svc.ErrorHandler = Depends()):
    try:
        DataStorageUpdate.model_validate(payload)
    except Exception as ex:
        res = {"error": {"code": 422, "message": f"Несоответствие входных данных: {ex}"}}
        app._logger.exception(res)
        await error_handler.handle_error(res)

    res = await app._update(payload=payload)
    await error_handler.handle_error(res)
    return res

@router.delete("/", status_code=202)
async def delete(payload: svc.NodeDelete, error_handler: svc.ErrorHandler = Depends()):
    res = await app._delete(payload)
    await error_handler.handle_error(res)
    return res

app.include_router(router, tags=["dataStorages"])
