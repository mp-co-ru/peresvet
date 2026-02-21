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

from fastapi import APIRouter, Depends

sys.path.append(".")

from src.common.base_svc import BaseSvc
from src.common.api_crud_svc import valid_uuid, ErrorHandler
from src.services.connectors.app_api.connectors_app_api_settings import ConnectorsAppAPISettings

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

        body = p.model_dump()

        res = await self._post_message(mes=body, reply=False, routing_key = f"{self._config.hierarchy['class']}.app_api.command.{body['id']}")
        # нет подписчика
        if res is None:
            res = {"error": {"code": 424, "message": f"Нет обработчика для отправки команды коннектору {body['id']}."}}
            app._logger.error(res["error"]["message"])
        return {}

settings = ConnectorsAppAPISettings()

app = ConnectorsAppAPI(settings=settings, title="`ConnectorsAppAPI` service")

router = APIRouter(prefix=f"{settings.api_version}/connectors_app")

@router.post("/", status_code=200)
async def command(payload: Command, error_handler: ErrorHandler = Depends()):
    """Отсылка команд коннекторам.

    .. http:example::
       :request: ../../../../docs/source/samples/connectors/sendCommandToConnectorIn.txt
       :response: ../../../../docs/source/samples/data/sendCommandToConnectorOut.txt

    **Параметры запроса:**

      * **id** (str) - идентификатор коннектора.
      * **command** ([str]) - список команд, которые должны быть выполнены коннектором.

    **Ответ:**

      {}

    """
    res = await app.command(payload)
    await error_handler.handle_error(res)
    return res

app.include_router(router, tags=["connectors_app"])
