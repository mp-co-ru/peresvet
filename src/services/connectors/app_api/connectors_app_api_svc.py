"""
Запись и получение исторических данных.

Подробно работа с историческими данными и примеры использования ключей в запросе
рассмотрены в разделе :ref:`historical_data`.
"""
import sys
import json
from typing import Any, List, NamedTuple
from typing_extensions import Annotated
from pydantic import (
    BaseModel, Field,
    field_validator, BeforeValidator, ConfigDict
)

from fastapi import APIRouter, Depends, Query

sys.path.append(".")

from src.common.base_svc import BaseSvc
from src.common.api_crud_svc import valid_uuid, ErrorHandler
from src.services.connectors.app_api.connectors_app_api_settings import ConnectorsAppAPISettings

from src.services.connectors.app.connectors_mqtt_app_svc import app as connectors_mqtt_app

class Command(BaseModel):
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

    id: str = Field(title="Идентификатор коннектора")
    command: dict = Field({}, title="Команда коннектору")

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: Any) -> Any:
        return valid_uuid(v)

class ConnectorsAppAPI(BaseSvc):
    """Сервис работы с коннекторами в иерархии.

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: ConnectorsAppAPISettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    def _set_handlers(self):
        self._handlers = {
            f"{self._config.hierarchy['class']}.app_api_client.command.*": self.command
        }

    async def command(self, mes: dict | Command, routing_key: str | None = None, error_handler: ErrorHandler = Depends()) -> dict:

        try:
            if isinstance(mes, dict):
                s = json.dumps(mes)
                p = Command.model_validate_json(s)
            else:
                p = mes

        except Exception as ex:
            res = {"error": {"code": 422, "message": f"Несоответствие входных данных: {ex}"}}
            app._logger.exception(res)
            await error_handler.handle_error(res)
        else:
            body = p.model_dump()

            post_res = await self._post_message(
                mes=body,
                reply=False,
                routing_key=f"{self._config.hierarchy['class']}.app_api.command.{body['id']}",
            )
            # нет подписчика на маршрут (сообщение не доставлено в брокер)
            if post_res is None:
                err = {
                    "error": {
                        "code": 424,
                        "message": f"Нет обработчика для отправки команды коннектору {body['id']}.",
                    }
                }
                app._logger.error(err["error"]["message"])
                return err
            return {"ok": True, "message": "Команда принята к доставке коннектору."}
        assert False, "unreachable"

settings = ConnectorsAppAPISettings()

app = ConnectorsAppAPI(settings=settings, title="`ConnectorsAppAPI` service")

router = APIRouter(prefix=f"{settings.api_version}/connectors_app")

@router.post("/", status_code=200)
async def command(payload: Command, error_handler: ErrorHandler = Depends()):
    """Отсылка команд коннекторам.

    .. http:example::
       :request: ../../../../docs/source/samples/connectors/sendCommandToConnectorIn.txt
       :response: ../../../../docs/source/samples/connectors/sendCommandToConnectorOut.txt

    **Параметры запроса:**

      * **id** (str) - идентификатор коннектора.
      * **command** (object) - тело команды: ``lines`` (список строк для ``os.system`` на стороне коннектора),
        опционально ``logToPlatform`` (bool) — включить/выключить дублирование лога в платформу по MQTT.

    **Ответ:**

      Успех: ``{"ok": true, "message": "..."}``. Ошибка доставки в брокер: HTTP 424 с телом ``{"detail": "..."}``.

    """
    res = await app.command(payload)
    await error_handler.handle_error(res)
    return res


@router.get("/link_status", status_code=200)
async def connector_link_status(
    id: str = Query(..., description="Идентификатор коннектора (UUID)"),
):
    """Состояние MQTT-связи коннектора с платформой (кэш сервиса ``connectors_mqtt_app``)."""
    valid_uuid(id)
    connected = id in connectors_mqtt_app._connected_connectors
    return {"id": id, "mqttConnected": connected}


@router.get("/log_tail", status_code=200)
async def connector_log_tail(
    id: str = Query(..., description="Идентификатор коннектора (UUID)"),
):
    """Последние строки лога, пришедшие от коннектора по MQTT (буфер ``connectors_mqtt_app``)."""
    valid_uuid(id)
    buf = connectors_mqtt_app._connector_log_lines.get(id)
    entries = list(buf) if buf else []
    return {"id": id, "entries": entries}


app.include_router(router, tags=["connectors_app"])
