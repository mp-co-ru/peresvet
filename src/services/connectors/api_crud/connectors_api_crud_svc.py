"""
Модуль содержит классы, описывающие входные данные для команд CRUD для коннекторов
и класс сервиса ``connectors_api_crud_svc``\.
"""
import sys
from pydantic import BaseModel, Field, validator, ConfigDict

from fastapi import APIRouter

sys.path.append(".")

from src.common import api_crud_svc as svc
from connectors_api_crud_settings import ConnectorsAPICRUDSettings

class LinkTagAttributes(svc.NodeAttributes):

    prsJsonConfigString: dict = Field(
        title="Параметры подключение к источнику данных.",
        description=(
            "Json, хранящий ключи, которые указывают коннектору, как "
            "получать значения тега из источника данных. "
            "Формат словаря зависит от конкретного коннектора."
        )
    )
    prsValueScale: int | None = Field(
        None,
        title=(
            "Коэффициент, на который умножается значение тега коннектором "
            "перед отправкой в платформу."
        )
    )
    prsMaxDev: int | None = Field(
        None,
        title="Величина значащего отклонения.",
        description="Используется коннекторами для снятия `дребезга` значений."
    )

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
        [],
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

router = APIRouter()

@router.post("/", response_model=svc.NodeCreateResult, status_code=201)
async def create(payload: ConnectorCreate):
    return await app.create(payload)

@router.get("/", response_model=ConnectorReadResult, status_code=200)
async def read(payload: ConnectorRead):
    return await app.read(payload)

@router.put("/", status_code=202)
async def update(payload: ConnectorUpdate):
    await app.update(payload)

@router.delete("/", status_code=202)
async def delete(payload: ConnectorRead):
    await app.delete(payload)

app.include_router(router, prefix=f"{settings.api_version}/connectors", tags=["connectors"])
