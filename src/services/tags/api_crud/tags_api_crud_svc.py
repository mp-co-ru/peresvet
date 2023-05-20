"""
Модуль содержит классы, описывающие входные данные для команд CRUD для тегов
и класс сервиса ``tags_api_crud_svc``.
"""
from uuid import UUID
from typing import Any, List
from pydantic import Field, validator

from fastapi import APIRouter

import src.common.api_crud_svc as svc
from .tags_api_crud_settings import TagsAPICRUDSettings

class TagCreateAttributes(svc.NodeCreateAttributes):
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
            "сжатия данных (в соответствии с параметром ``prsMaxLineDev``). "
            "**Не используется**."
        )
    )
    prsMaxDev: float = Field(
        0,
        title="Величина значащего отклонения.",
        description="Используется коннекторами для снятия `дребезга` значений."
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
    prsStore: dict = Field(
        None,
        title="Словарь, описывающий способ хранения данных тега.",
        description=(
            "Для реляционных баз данных - имя таблицы, "
            "для Victoriametrics - имя метрики и теги параметра."
        )
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
    prsValueScale: float = Field(
        1,
        title=(
            "Коэффициент, на который умножается значение тега коннектором "
            "перед отправкой в платформу."
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
    prsDefaultValue: Any = Field(
        None,
        title="Значение тега по умолчанию.",
        description=(
            "Если присутствует, то указанное значение записывается "
            "в хранилище при создании тега с меткой времени на момент создания."
        )
    )
    prsMeasureUnits: str = Field(
        None,
        title="Единицы измерения тега."
    )
    prsSource: dict = Field(
        None,
        title="Словарь источника данных.",
        description=(
            "Значения ключей словаря указывают коннектору, как "
            "получать значения тега из источника данных. "
            "Формат словаря зависит от конкретного коннектора."
        )
    )

class TagCreate(svc.NodeCreate):
    dataStorageId: str = Field(
        None,
        title="Id хранилища данных, в котором будет храниться история значений тега.",
        description="Если = None, тег будет привязан к хранилищу по умолчанию."
    )
    connectorId: str = Field(
        None,
        title="Id коннектора-поставщика данных."
    )
    attributes: TagCreateAttributes = Field(title="Атрибуты узла")

    validate_id = validator('parentId', 'dataStorageId', 'connectorId', allow_reuse=True)(svc.valid_uuid)

class TagRead(svc.NodeRead):
    getDataStorageId: bool = Field(
        False,
        title="Флаг возврата id хранилища данных."
    )
    getDataSourceId: bool = Field(
        False,
        title="Флаг возврата id источника данных."
    )

class OneTagInReadResult(svc.OneNodeInReadResult):
    dataStorageId: str = Field(None, title="Id хранилища данных.")
    dataSourceId: dict = Field(None, title="Id источника данных.")

class TagReadResult(svc.NodeReadResult):
    data: List[OneTagInReadResult] = Field(title="Список тегов.")

class TagUpdate(svc.NodeUpdate):
    dataStorageId: str = Field(
        None,
        title="Id хранилища данных, в котором будет храниться история значений тега.",
        description="Если = None, тег будет привязан к хранилищу по умолчанию."
    )
    connectorId: str = Field(
        None,
        title="Id коннектора-поставщика данных."
    )

    validate_id = validator('parentId', 'id', 'dataStorageId', 'connectorId', allow_reuse=True)(svc.valid_uuid)

class TagsAPICRUD(svc.APICRUDSvc):
    """Сервис работы с тегами в иерархии.

    Подписывается на очередь ``tags_api_crud`` обменника ``tags_api_crud``,
    в которую публикует сообщения сервис ``tags_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

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

router = APIRouter()

@router.post("/", response_model=svc.NodeCreateResult, status_code=201)
async def create(payload: TagCreate):
    return await app.create(payload)

@router.get("/", response_model=svc.NodeCreateResult, status_code=201)
async def read(payload: TagRead):
    return await app.create(payload)

@router.put("/", status_code=202)
async def update(payload: TagUpdate):
    await app.update(payload)

@router.delete("/", status_code=202)
async def delete(payload: TagRead):
    await app.delete(payload)

app.include_router(router, prefix=f"{settings.api_version}/tags", tags=["tags"])
