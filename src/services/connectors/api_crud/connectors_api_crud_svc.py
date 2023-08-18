"""
Модуль содержит классы, описывающие входные данные для команд CRUD для коннекторов
и класс сервиса ``connectors_api_crud_svc``.
"""
import sys
from typing import List
from pydantic import Field
from typing import Optional, List

from fastapi import APIRouter

sys.path.append(".")

from src.common import api_crud_svc as svc
from connectors_api_crud_settings import ConnectorsAPICRUDSettings


class ConnectorCreateAttributes(svc.NodeAttributes):
    pass

class ConnectorLinkedTagAttributes(svc.NodeAttributes):
    prsSource: dict = Field(
        None,
        title="Словарь источника данных.",
        description=(
            "Значения ключей словаря указывают коннектору, как "
            "получать значения тега из источника данных. "
            "Формат словаря зависит от конкретного коннектора."
        )
    )
    prsValueScale: int = Field(
        None,
        title=(
            "Коэффициент, на который умножается значение тега коннектором "
            "перед отправкой в платформу."
        )
    )
    prsMaxDev: int = Field(
        None,
        title="Величина значащего отклонения.",
        description="Используется коннекторами для снятия `дребезга` значений."
    )

class ConnectorLinkedTag(svc.NodeRead):
    attributes: ConnectorLinkedTagAttributes = Field(title="Атрибуты тега")

class ConnectorLinkedTagUpdate(svc.NodeUpdate):
    attributes: Optional[ConnectorLinkedTagAttributes] = Field(title="Аттрибуты узла опционально")

class ConnectorCreate(svc.NodeCreate):
    attributes: ConnectorCreateAttributes = Field(title="Атрибуты узла")
    linkTags: list[ConnectorLinkedTag] = Field(title="Список добавленных тегов для коннектора")
    # validate_id = validator('parentId', 'dataStorageId', 'connectorId', allow_reuse=True)(svc.valid_uuid)

class ConnectorRead(svc.NodeRead):
    pass

class OneConnectorInReadResult(svc.OneNodeInReadResult):
    pass

class ConnectorReadResult(svc.NodeReadResult):
    data: List[OneConnectorInReadResult] = Field(title="Список коннекторов")

class ConnectorUpdate(svc.NodeUpdate):
    linkTags: Optional[List[ConnectorLinkedTagUpdate]] = Field(title="Список добавленных тегов для коннектора")
    unlinkTags: Optional[List[str]] = Field(title="Список отсоединенных тегов для коннектора")

class ConnectorsAPICRUD(svc.APICRUDSvc):
    """Сервис работы с коннекторами в иерархии.

    Подписывается на очередь ``connectors_api_crud`` обменника ``connectors_api_crud``,
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

@router.get("/", response_model=svc.NodeReadResult, status_code=200)
async def read(payload: ConnectorRead):
    return await app.read(payload)

@router.put("/", status_code=202)
async def update(payload: ConnectorUpdate):
    await app.update(payload)

@router.delete("/", status_code=202)
async def delete(payload: ConnectorRead):
    await app.delete(payload)

@router.get('/test')
async def test():
    return {"test": "ok"}

app.include_router(router, prefix=f"{settings.api_version}/connectors", tags=["connectors"])
