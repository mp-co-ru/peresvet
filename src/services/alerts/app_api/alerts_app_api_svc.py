"""
Модуль содержит классы, описывающие входные данные для команд CRUD для тегов
и класс сервиса ``tags_api_crud_svc``.
"""
import sys
from typing import Any, List, NamedTuple
from typing_extensions import Annotated
from pydantic import BaseModel, Field, field_validator, validator, BeforeValidator, ValidationError
import json

from fastapi import APIRouter
from fastapi import WebSocket

sys.path.append(".")

from src.common import svc
from src.common.api_crud_svc import valid_uuid
from src.services.alerts.app_api.alerts_app_api_settings import AlertsAppAPISettings
import src.common.times as t

class AlarmsGet(BaseModel):
    """
    Логика получения алярмов:
    parentId: указываем объект (список объектов), алярмы которого хотим получить
    getChildren: флаг учёта дочерних объектов
    format: флаг форматирования меток времени в ответе на запрос

    Запрос возвращает активные алярмы, либо неактивные и неквитированные.

    Возвращение истории алярмов (использование флагов start и finish) - в следующей версии.
    """
    parentId: str | list[str] = Field(None, title="Объект, тревоги которого запрашиваем.")
    getChildren: bool = Field(False, title="Учитывать тревоги дочерних объектов.")
    format: bool = Field(False, title="Флаг форматирования меток времени.")

    validate_id = validator('parentId', allow_reuse=True)(valid_uuid)

    @validator('parentId')
    @classmethod
    def tagId_list(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [v]
        else:
            return v

class AlarmData(BaseModel):
    id: str = Field(title="Id тревоги.")
    description: str = Field(title="Описание тревоги.")
    start: int | str = Field(title="Время возникновения тревоги.")
    finish: int | str = Field(None, title="Время пропадания тревоги.")
    acked: int | str = Field(None, title="Время квитирования тревоги.")

class AckAlarm(BaseModel):
    id: str = Field(title="Id тревоги.")
    x: int | str = Field(None, title="Время квитирования тревоги.")

    @validator('x')
    @classmethod
    def ts_in_iso_format(cls, v: Any) -> int:
        try:
            return t.ts(v)
        except ValueError as ex:
            raise ValueError(
                (
                    "Метка времени должна быть строкой в формате ISO8601, "
                    "целым числом или отсутствовать."
                )
            )

    validate_id = validator('id', allow_reuse=True)(valid_uuid)

class AlertsAppAPI(svc.Svc):
    """Сервис работы с тегами в иерархии.

    Подписывается на очередь ``tags_api_crud`` обменника ``tags_api_crud``,
    в которую публикует сообщения сервис ``tags_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    _outgoing_commands = {}

    def __init__(self, settings: AlertsAppAPISettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def alarms_get(self, payload: AlarmsGet) -> dict:

        body = {
            "action": "alerts.getAlarms",
            "data": payload.model_dump()
        }

        res = await self._post_message(mes=body, reply=True)
        return res

    async def ack_alarm(self, payload: AckAlarm) -> None:
        body = {
            "action": "alerts.ackAlarms",
            "data": payload.model_dump()
        }

        return await self._post_message(mes=body, reply=False)

settings = AlertsAppAPISettings()

app = AlertsAppAPI(settings=settings, title="`TagsAppAPI` service")

router = APIRouter()

@router.get("/", response_model=dict, status_code=200)
async def alarms_get(payload: AlarmsGet):
    res = await app.alarms_get(payload)
    return res

@router.put("/", status_code=200)
async def ack_alarm(payload: AckAlarm):
    return await app.ack_alarm(payload)

'''
@app.websocket(f"{settings.api_version}/ws/data")
async def websocket_endpoint(websocket: WebSocket):

    try:
        await websocket.accept()
        app._logger.debug(f"Установлена ws-связь.")

        while True:
            try:
                received_data = await websocket.receive_json()
                action = received_data.get("action")
                if not action:
                    raise ValueError("Не указано действие в команде.")
                data = received_data.get("data")
                if not data:
                    raise ValueError("Не указаны данные команды.")

                match action:
                    case "get":
                        res = await app.data_get(DataGet(**data))
                    case "set":
                        await app.data_set(AllData(**data))
                        res = {
                            "error": {"id": 0}
                        }
                await websocket.send_json(res)

            except TypeError as ex:
                app._logger.error(f"Неверный формат данных: {ex}")
            except ValidationError as ex:
                app._logger.error(f"Неверные данные сообщения: {ex}")
            except json.JSONDecodeError as ex:
                app._logger.error(f"Сообщение должно быть в виде json: {ex}")
            except ValueError as ex:
                app._logger.error(ex)

    except Exception as ex:
        app._logger.error(f"Разрыв ws-связи: {ex}")
'''

app.include_router(router, prefix=f"{settings.api_version}/alarms", tags=["alarms"])
