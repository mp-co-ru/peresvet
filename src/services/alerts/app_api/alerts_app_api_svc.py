"""
Модуль содержит классы, описывающие входные данные для команд тревог
и класс сервиса ``alerts_app_api_svc``.
"""
import sys
from typing import Any
from pydantic import (
    BaseModel, Field, field_validator, ConfigDict
)

from fastapi import APIRouter, HTTPException, Query

sys.path.append(".")

from src.common import svc
from src.common.api_crud_svc import valid_uuid
from src.common.authorization import authorize_action
from src.services.alerts.app_api.alerts_app_api_settings import AlertsAppAPISettings
import src.common.times as t

class AlarmsGet(BaseModel):
    """
    Логика получения алярмов:
    parentId: объект, тег или тревога (либо их список). По умолчанию None.
    getChildren: учитывать дочерние объекты. По умолчанию False.

    Без parentId и без getChildren — активные алярмы объектов верхнего
    уровня и всех тегов из папки «Теги». Без parentId, но с getChildren —
    алярмы всей ветки объектов и той же папки «Теги».

    format: форматировать метки времени. По умолчанию False.
    fired: только активные алярмы. По умолчанию True. False — все алярмы.
    start: начало интервала по метке срабатывания. По умолчанию None.
    finish: конец интервала. По умолчанию текущее время.
    count: сколько алярмов вернуть по каждой тревоге. Если fired = True, count игнорируется.

    fired без start и count — эпизод, активный в момент finish.
    fired=false без start и count — состояние каждой тревоги в момент finish.
    fired=false вместе со start или count — список срабатываний.
    """
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

    parentId: str | list[str] = Field(None, title="Объект, тег или тревога.")
    getChildren: bool = Field(False, title="Учитывать тревоги дочерних объектов.")
    format: bool = Field(False, title="Флаг форматирования меток времени.")
    fired: bool = Field(True, title="Флаг возврата только активных алярмов.")
    start: int | str | None = Field(None, title="Начало интервала по метке срабатывания.")
    finish: int | str | None = Field(None, title="Момент или конец интервала.")
    count: int | None = Field(None, title="Сколько алярмов вернуть по каждой тревоге.")

    @field_validator("parentId")
    @classmethod
    def tagId_list(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [v]
        else:
            return v

    @field_validator("parentId")
    @classmethod
    def validate_id(cls, v: Any) -> Any:
        return valid_uuid(v)

    @field_validator("start", "finish")
    @classmethod
    def optional_ts(cls, v: Any) -> int | None:
        if v is None or v == "":
            return None
        try:
            return t.ts(v)
        except ValueError as ex:
            raise ValueError(
                "Метка времени должна быть строкой ISO8601 или целым числом микросекунд."
            ) from ex

    @field_validator("count")
    @classmethod
    def count_bounds(cls, v: int | None) -> int | None:
        if v is None:
            return None
        if v < 1:
            return 1
        if v > 500:
            return 500
        return v


class AlarmData(BaseModel):
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

    id: str = Field(title="Id тревоги.")
    cn: str = Field(title="Имя тревоги.")
    description: str = Field("", title="Описание тревоги.")
    tagId: str = Field("", title="Тег, на котором висит тревога.")
    fired: int | str | None = Field(None, title="Время возникновения тревоги.")
    finish: int | str | None = Field(None, title="Время пропадания тревоги.")
    acked: int | str | None = Field(None, title="Время квитирования тревоги.")

class AckAlarm(BaseModel):
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

    id: str = Field(title="Id тревоги.")
    x: int | str | None = Field(
        None,
        validate_default=True,
        title="Время квитирования тревоги.",
    )

    @field_validator("x")
    @classmethod
    def ts_in_iso_format(cls, v: Any) -> int:
        try:
            # Нет метки — квитируем текущим моментом. Валидатор должен
            # сработать и на значении по умолчанию.
            return t.ts(v)
        except ValueError as ex:
            raise ValueError(
                (
                    "Метка времени должна быть строкой в формате ISO8601, "
                    "целым числом или отсутствовать."
                )
            ) from ex

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: Any) -> Any:
        return valid_uuid(v)

class AlertsAppAPI(svc.Svc):
    """Сервис работы с тегами в иерархии.

    Подписывается на очередь ``tags_api_crud`` обменника ``tags_api_crud``,
    в которую публикует сообщения сервис ``tags_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: AlertsAppAPISettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def alarms_get(self, payload: AlarmsGet) -> dict:

        body = payload.model_dump()
        await authorize_action(
            f"{self._config.hierarchy['class']}.alarm_read",
            resource={"parentIds": body.get("parentId")},
            payload=body,
        )

        res = await self._post_message(
            mes=body,
            reply=True,
            routing_key=f"{self._config.hierarchy['class']}.app_api.get_alarms")
        if not isinstance(res, dict):
            raise HTTPException(status_code=503, detail="Сервис тревог не ответил.")
        if res.get("error") and "data" not in res:
            err = res["error"] if isinstance(res["error"], dict) else {}
            raise HTTPException(
                status_code=int(err.get("code") or 500),
                detail=err.get("message") or "Ошибка чтения тревог.",
            )
        res.setdefault("data", [])

        if payload.format:
            for alarm_item in res["data"]:
                for key in ("fired", "finish", "acked"):
                    value = alarm_item.get(key)
                    alarm_item[key] = t.int_to_local_timestamp(value) if value else None

        return res

    async def ack_alarm(self, payload: AckAlarm) -> None:
        body = payload.model_dump()
        await authorize_action(
            f"{self._config.hierarchy['class']}.alarm_ack",
            resource={"id": body["id"]},
            payload=body,
        )

        return await self._post_message(
            mes=body,
            reply=False,
            routing_key=f"{self._config.hierarchy['class']}.app_api.ack_alarm"
        )

settings = AlertsAppAPISettings()

app = AlertsAppAPI(settings=settings, title="`AlertsAppAPI` service")

router = APIRouter(prefix=f"{settings.api_version}/alarms")

@router.get("/", response_model=dict, status_code=200, response_model_exclude_none=True)
async def alarms_get(
    parentId: list[str] | None = Query(None),
    getChildren: bool = False,
    format: bool = False,
    fired: bool = True,
    alertId: str | None = None,
    start: str | None = None,
    finish: str | None = None,
    count: int | None = None,
    q: str | None = None,
):
    if q:
        payload = AlarmsGet.model_validate_json(q)
    else:
        # alertId оставлен как ещё один parentId: тревога читается тем же запросом.
        parents = list(parentId or [])
        if alertId:
            parents.append(alertId)
        body = {
            "getChildren": getChildren,
            "format": format,
            "fired": fired,
            "start": start,
            "finish": finish,
            "count": count,
        }
        if parents:
            body["parentId"] = parents
        payload = AlarmsGet.model_validate(body)

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
