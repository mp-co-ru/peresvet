"""
Запись и получение исторических данных.

Подробно работа с историческими данными и примеры использования ключей в запросе
рассмотрены в разделе :ref:`historical_data`.
"""
import sys
import asyncio
import base64
import json
import os
from typing import Any, List, NamedTuple
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from typing_extensions import Annotated
from pydantic import (
    BaseModel, Field,
    field_validator, BeforeValidator, ConfigDict
)

from fastapi import APIRouter, Depends, Query

sys.path.append(".")

from src.common.base_svc import BaseSvc
from src.common.api_crud_svc import valid_uuid, ErrorHandler
from src.common.logger import PrsLogBuffer
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

    def _rabbitmq_management_settings(self) -> tuple[str, str]:
        amqp_url = self._config.broker.get("amqp_url", "")
        parsed = urlparse(amqp_url)
        host = parsed.hostname or os.getenv("RABBIT_HOST", "rabbitmq")
        port = os.getenv("RABBIT_UI_PORT", "15672")
        user = parsed.username or os.getenv("RABBITMQ_DEFAULT_USER", "guest")
        password = parsed.password or os.getenv("RABBITMQ_DEFAULT_PASS", "guest")
        vhost = parsed.path.lstrip("/") or "/"
        queues_url = f"http://{host}:{port}/api/queues/{quote(vhost, safe='')}"
        auth_token = base64.b64encode(f"{user}:{password}".encode()).decode()
        return queues_url, auth_token

    @staticmethod
    def _fetch_rabbitmq_json(url: str, auth_token: str) -> Any:
        request = Request(url, headers={"Authorization": f"Basic {auth_token}"})
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _service_items_from_names(names: list[str]) -> list[dict]:
        return [
            {
                "name": name,
                "queues": [],
                "consumers": 0,
                "messages": 0,
                "state": "registered",
            }
            for name in sorted({name for name in names if name})
        ]

    @staticmethod
    def _service_items_from_queues(queues: list[dict]) -> list[dict]:
        services = {}
        for queue in queues:
            queue_name = str(queue.get("name") or "")
            if "_consume" not in queue_name:
                continue
            service_name = queue_name.split("_consume", 1)[0]
            if not service_name:
                continue
            current = services.setdefault(
                service_name,
                {
                    "name": service_name,
                    "queues": [],
                    "consumers": 0,
                    "messages": 0,
                    "state": "unknown",
                },
            )
            current["queues"].append(queue_name)
            current["consumers"] += int(queue.get("consumers") or 0)
            current["messages"] += int(queue.get("messages") or 0)
            if queue.get("state"):
                current["state"] = queue["state"]
        return sorted(services.values(), key=lambda item: item["name"])

    async def list_rabbitmq_services(self) -> dict:
        queues_url, auth_token = self._rabbitmq_management_settings()
        try:
            queues = await asyncio.to_thread(
                self._fetch_rabbitmq_json, queues_url, auth_token
            )
            services = self._service_items_from_queues(queues)
            if services:
                return {"services": services, "source": "rabbitmq"}
        except Exception as ex:
            self._logger.warning(
                f"{self._config.svc_name} :: Не удалось получить список сервисов из RabbitMQ management API: {ex}"
            )

        return {
            "services": self._service_items_from_names(BaseSvc.registered_service_names()),
            "source": "runtime",
        }

    def service_log_tail(self, service_names: list[str], limit: int = 400) -> dict:
        safe_services = sorted({name.strip() for name in service_names if name and name.strip()})
        limit = max(1, min(int(limit or 400), 2000))
        entries = PrsLogBuffer.tail(safe_services, limit)
        result = []
        for name in safe_services:
            service_lines = [
                entry["line"]
                for entry in entries
                if entry.get("service") == name
                or str(entry.get("message", "")).startswith((f"{name} ::", f"{name}:"))
            ]
            result.append({"name": name, "lines": service_lines[-limit:]})
        return {"entries": entries, "services": result}

    def clear_service_log_tail(self, service_names: list[str]) -> dict:
        safe_services = sorted({name.strip() for name in service_names if name and name.strip()})
        cleared = PrsLogBuffer.clear(safe_services)
        return {"ok": True, "cleared": cleared, "services": safe_services}

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
      * **command** (object) - тело команды: ``lines`` (список строк, каждая выполняется в shell на стороне коннектора
        через ``subprocess``); результат каждой строки публикуется в платформу по MQTT отдельным действием
        ``prsConnector.command_output`` (не смешивается с ``prsConnector.log_line``). Список последних результатов:
        ``GET .../command_output_tail?id=<uuid>``;
        опционально ``logToPlatform`` (bool) — включить/выключить дублирование **файлового** лога в платформу по ``log_line``;
        опционально ``timeoutSec`` (число, по умолчанию 120) — таймаут на одну строку;
        ``maxOutputBytes`` (int, по умолчанию 65536) — ограничение длины stdout/stderr до усечения.

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


@router.get("/command_output_tail", status_code=200)
async def connector_command_output_tail(
    id: str = Query(..., description="Идентификатор коннектора (UUID)"),
):
    """Последние результаты удалённых команд (``prsConnector.command_output``), отдельно от ``log_tail``."""
    valid_uuid(id)
    buf = connectors_mqtt_app._connector_command_output_lines.get(id)
    entries = list(buf) if buf else []
    return {"id": id, "entries": entries}


@router.get("/services", status_code=200)
async def rabbitmq_services():
    """Сервисы, зарегистрированные в RabbitMQ как consume-очереди."""
    return await app.list_rabbitmq_services()


@router.get("/service_log_tail", status_code=200)
async def service_log_tail(
    service: List[str] = Query([], description="Имя сервиса; можно передать несколько раз"),
    limit: int = Query(400, ge=1, le=2000, description="Количество последних строк на сервис"),
    clear: bool = Query(False, description="Очистить буфер перед чтением"),
):
    """Последние строки общего лога платформы, отфильтрованные по выбранным сервисам."""
    if clear:
        app.clear_service_log_tail(service)
        return {"entries": [], "services": [], "cleared": True}
    return app.service_log_tail(service, limit)


@router.delete("/service_log_tail", status_code=200)
async def clear_service_log_tail(
    service: List[str] = Query([], description="Имя сервиса; можно передать несколько раз"),
):
    """Очистить in-memory буфер журнала для выбранных сервисов."""
    return app.clear_service_log_tail(service)


app.include_router(router, tags=["connectors_app"])
