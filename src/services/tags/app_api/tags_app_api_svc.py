"""
Модуль содержит классы, описывающие входные данные для команд CRUD для тегов
и класс сервиса ``tags_api_crud_svc``.
"""
import sys
import asyncio
import copy
from uuid import UUID
from typing import Any, List
from pydantic import BaseModel, Field, validator

from fastapi import APIRouter

sys.path.append(".")

from src.common import svc
from src.common.api_crud_svc import valid_uuid
from src.services.tags.app_api.tags_app_api_settings import TagsAppAPISettings
import src.common.times as t

class DataPointItem(BaseModel):
    x: int | str | None = Field(
        t.now_int(),
        title="Метка времени",
        description=(
            "Метка времени значения. Может быть: "
            "строкой в формате ISO8601; "
            "целым числом, в этом случае число - количество микросекунд, "
            "начиная с 1 января 1970 года; NULL - тогда платформа присваивает "
            "в качестве метки времени текущий момент."
        )
    )
    y: float | dict | str | int | None = Field(
        None,
        title="Значение тега"
    )
    q: int | None = Field(
        None,
        title="Качество значения",
        description="None = хорошее качество значения."
    )

    @validator('x')
    @classmethod
    def x_in_iso_format(cls, v: Any) -> int:
        # если x в виде строки, то строка должна быть в формате ISO9601
        try:
            return t.ts(v)
        except ValueError as ex:
            raise ValueError(
                (
                    "Метка времени должна быть строкой в формате ISO8601, "
                    "целым числом или отсутствовать."
                )
            )

class TagData(BaseModel):
    tagId: str = Field(
        title="id тега"
    )
    data: List[DataPointItem] = Field(
        "Данные тега"
    )

    validate_id = validator('tagId', allow_reuse=True)(valid_uuid)

class AllData(BaseModel):
    data: List[TagData] = Field(
        title="Данные"
    )

class DataGet(BaseModel):
    tagId: str | list[str] = Field(
        title="Id или список id тегов"
    )
    start: int | str = Field(
        None,
        title="Метка времени начала периода."
    )
    finish: int | str = Field(
        t.now_int(),
        title="Метка времени окончания периода."
    )
    maxCount: int = Field(
        None,
        title="Максимальное количество точек в ответе."
    )
    format: bool = Field(
        False,
        title="Флаг форматирования меток времени в строку формата ISO8601"
    )
    actual: bool = Field(
        False,
        title="Флаг возврата только реально записанных данных."
    )
    value: Any = Field(
        None,
        title="Фильтр по значению"
    )
    count: int = Field(
        None,
        title="Количество запрашиваемых точек."
    )
    timeStep: int = Field(
        None,
        title="Шаг между соседними значениями."
    )

    @validator('tagId')
    @classmethod
    def tagId_list(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [v]
        else:
            return v

    @validator('finish')
    @classmethod
    def finish_in_iso_format(cls, v: Any) -> int:
        # если finish в виде строки, то строка должна быть в формате ISO9601
        try:
            return t.ts(v)
        except ValueError as ex:
            raise ValueError(
                (
                    "Метка времени должна быть строкой в формате ISO8601, "
                    "целым числом или отсутствовать."
                )
            )

    @validator('start')
    @classmethod
    def start_in_iso_format(cls, v: Any) -> int:
        if v is None:
            return
        # если finish в виде строки, то строка должна быть в формате ISO9601
        try:
            return t.ts(v)
        except ValueError as ex:
            raise ValueError(
                (
                    "Метка времени должна быть строкой в формате ISO8601, "
                    "целым числом или отсутствовать."
                )
            )

    validate_id = validator('tagId', allow_reuse=True)(valid_uuid)

class TagsAppAPI(svc.Svc):
    """Сервис работы с тегами в иерархии.

    Подписывается на очередь ``tags_api_crud`` обменника ``tags_api_crud``,
    в которую публикует сообщения сервис ``tags_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    _outgoing_commands = {}

    def __init__(self, settings: TagsAppAPISettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def data_get(self, payload: DataGet) -> dict:
        body = {
            "action": "tags.get_data",
            "data": payload.dict()
        }

        return await self._post_message(mes=body, reply=True)

    async def data_set(self, payload: AllData) -> None:
        body = {
            "action": "tags.set_data",
            "data": payload.dict()
        }

        return await self._post_message(mes=body, reply=False)

settings = TagsAppAPISettings()

app = TagsAppAPI(settings=settings, title="`TagsAppAPI` service")

router = APIRouter()

@router.get("/", response_model=AllData, status_code=200)
async def data_get(payload: DataGet):
    return await app.data_get(payload)

@router.post("/", status_code=200)
async def data_set(payload: AllData):
    return await app.data_set(payload)

app.include_router(router, prefix=f"{settings.api_version}/data", tags=["data"])
