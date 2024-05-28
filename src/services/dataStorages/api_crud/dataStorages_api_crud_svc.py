"""
Модуль содержит классы, описывающие входные данные для команд CRUD для хранилищ данных
и класс сервиса ``dataStorages_api_crud_svc``\.
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
    objectClass: str = Field(title="Класс узла")

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

    _outgoing_commands = {
        "create": "dataStorages.create",
        "read": "dataStorages.read",
        "update": "dataStorages.update",
        "delete": "dataStorages.delete"
    }

    def __init__(self, settings: DataStoragesAPICRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def create(self, payload: DataStorageCreate) -> dict:
        return await super().create(payload=payload)

    async def read(self, payload: DataStorageRead) -> dict:
        return await super().read(payload=payload)

    async def update(self, payload: DataStorageUpdate) -> dict:
        return await super().update(payload=payload)

settings = DataStoragesAPICRUDSettings()

app = DataStoragesAPICRUD(settings=settings, title="`DataStoragesAPICRUD` service")

router = APIRouter(prefix=f"{settings.api_version}/dataStorages")

error_handler = svc.ErrorHandler()

@router.post("/", response_model=svc.NodeCreateResult, status_code=201)
async def create(payload: DataStorageCreate, error_handler: svc.ErrorHandler = Depends()):
    res = await app.create(payload)
    await error_handler.handle_error(res)
    return res

@router.get("/", response_model=DataStorageReadResult | None, status_code=200)
async def read(q: str | None = None, payload: DataStorageRead | None = None, error_handler: svc.ErrorHandler = Depends()):
    res = await app.api_get_read(DataStorageRead, q, payload)
    await error_handler.handle_error(res)
    return res

@router.put("/", status_code=202)
async def update(payload: DataStorageUpdate, error_handler: svc.ErrorHandler = Depends()):
    res = await app.update(payload)
    await error_handler.handle_error(res)
    return res

@router.delete("/", status_code=202)
async def delete(payload: svc.NodeDelete, error_handler: svc.ErrorHandler = Depends()):
    res = await app.delete(payload)
    await error_handler.handle_error(res)
    return res

app.include_router(router, tags=["dataStorages"])
