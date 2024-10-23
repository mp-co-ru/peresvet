"""
Модуль содержит классы, описывающие входные данные для команд тревог
и класс сервиса ``alerts_app_api_svc``\.
"""
import sys
from typing import Any
from pydantic import (
    BaseModel, Field, validator, ConfigDict
)

from fastapi import APIRouter

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
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

    parentId: str | list[str] = Field(None, title="Объект, тревоги которого запрашиваем.")
    getChildren: bool = Field(False, title="Учитывать тревоги дочерних объектов.")
    format: bool = Field(False, title="Флаг форматирования меток времени.")
    fired: bool = Field(True, title="Флаг возврата только активных алярмов.")

    validate_id = validator('parentId', allow_reuse=True)(valid_uuid)

    @validator('parentId')
    @classmethod
    def tagId_list(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [v]
        else:
            return v

class AlarmData(BaseModel):
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

    id: str = Field(title="Id тревоги.")
    cn: str = Field(title="Имя тревоги.")
    description: str = Field(title="Описание тревоги.")
    start: int | str = Field(title="Время возникновения тревоги.")
    finish: int | str = Field(None, title="Время пропадания тревоги.")
    acked: int | str = Field(None, title="Время квитирования тревоги.")

class AckAlarm(BaseModel):
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

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

    Подписывается на очередь ``tags_api_crud`` обменника ``tags_api_crud``\,
    в которую публикует сообщения сервис ``tags_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: AlertsAppAPISettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def alarms_get(self, payload: AlarmsGet) -> dict:

        body = payload.model_dump()

        res = await self._post_message(
            mes=body, 
            reply=True, 
            routing_key=f"{self._config.hierarchy['class']}.app_api.get_alarms")

        if payload.format:
            for alarm_item in res["data"]:
                alarm_item["fired"] = t.int_to_local_timestamp(alarm_item["fired"])
                if alarm_item["acked"] is not None:
                    alarm_item["acked"] = t.int_to_local_timestamp(alarm_item["acked"])

        return res

    async def ack_alarm(self, payload: AckAlarm) -> None:
        body = payload.model_dump()

        return await self._post_message(
            mes=body, 
            reply=False,
            routing_key=f"{self._config.hierarchy['class']}.app_api.ack_alarm"
        )

settings = AlertsAppAPISettings()

app = AlertsAppAPI(settings=settings, title="`AlertsAppAPI` service")

router = APIRouter(prefix=f"{settings.api_version}/alarms")

@router.get("/", response_model=dict, status_code=200, response_model_exclude_none=True)
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

app.include_router(router, tags=["alarms"])
