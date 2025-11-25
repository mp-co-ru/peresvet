import sys
import json

from fastapi import APIRouter
import aio_pika
import aio_pika.abc
sys.path.append(".")

from src.services.connectors.app.connectors_mqtt_app_settings import ConnectorsMQTTAppSettings
from src.common.app_svc import AppSvc
from src.common import hierarchy
import src.common.times as t

class ConnectorsMQTTApp(AppSvc):
    """Сервис работы с коннекторами.

    Подписывается на очередь ``connectors_tags_api`` обменника ``connectors_api_crud``,
    в которую публикует сообщения сервис ``connectors_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: ConnectorsMQTTAppSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    def _add_app_handlers(self):
        self._handlers["conn2prs.*"] = self._send_config_to_connector
        self._handlers[f"{self._config.hierarchy['class']}.model.tag_updated.*"] = self._tags_updated
        self._handlers[f"{self._config.hierarchy['class']}.model.tag_deleted.*"] = self._tag_deleted
        self._handlers[f"{self._config.hierarchy['class']}.model.tag_link_updated.*"] = self._tags_updated
        self._handlers[f"{self._config.hierarchy['class']}.model.unlink_tag.*"] = self._tags_unlinked
        self._handlers[f"{self._config.hierarchy['class']}.model.link_tag.*"] = self._tag_linked
        self._handlers[f"{self._config.hierarchy['class']}.app_api.command.*"] = self._send_command

    async def _tag_linked(self, mes: dict, routing_key: str | None = None):
        conn_id = mes["connectorId"]
        tags = mes["tagId"]
        if isinstance(tags, str):
            tags = [tags]

        tags_data = {}
        for tag_id in tags:
            tags_data[tag_id] = await self._get_tag_data(conn_id=conn_id, tag_id=tag_id)

        mes2conn = {
            "action": "prsConnector.tags_configuration",
            "data": {
                "tags": tags_data
            }
        }
        await self._post_message(mes=mes2conn, routing_key=f"prs2conn.{conn_id}")
        self._logger.info(f"{self._config.svc_name} :: Коннектору {conn_id} послано сообщение о привязке тега {tags}.")

    async def _send_command(self, mes: dict, routing_key: str | None = None):
        mes2conn = {
            "action": "prsConnector.command",
            "data": mes
        }
        conn_id = mes["id"]
        await self._post_message(mes=mes2conn, routing_key=f"prs2conn.{conn_id}")
        self._logger.info(f"{self._config.svc_name} :: Коннектору {conn_id} посланы команды: {mes['command']['lines']}.")

    async def _find_connector_by_tag(self, tag_id: str) -> list[str]:
        if not self._config.nodes: # type: ignore
            payload = {
                "base": "cn=connectors,cn=prs",
                "scope": hierarchy.CN_SCOPE_ONELEVEL,
                "filter": {"objectClass": ["prsConnector"]}
            }
            res = await self._hierarchy.search(payload)
            connectors = [res_item[0] for res_item in res]
        else:
            connectors = self._config.nodes # type: ignore

        if not connectors:
            return []

        result = []
        for conn_id in connectors:
            payload = {"base": conn_id, "filter": {"cn": [tag_id]}}
            res = await self._hierarchy.search(payload)
            if res:
                result.append(conn_id)
        return result

    async def _tags_updated(self, mes: dict, routing_key: str | None = None):
        # TODO: по правильному, чтобы получить данные по какой-либо сущности,
        # необходимо делать запрос соответствующему сервису,
        # но, так как система сообщений ещё не устоялась,
        # будем искать данные сразу в иерархии

        # сервис prsConnector.model сам ищет привязки тега к коннекторам
        # и для каждого посылает сообщение, поэтому здесь не ищем список привязки тега

        tags = mes["tagId"]
        if isinstance(tags, str):
            tags = [tags]
        conn_id = mes["connectorId"]

        tags_data = {}
        for tag_id in tags:
            tags_data[tag_id] = await self._get_tag_data(conn_id=conn_id, tag_id=tag_id)

        mes2conn = {
            "action": "prsConnector.tags_configuration",
            "data": {
                "tags": tags_data
            }
        }

        await self._post_message(mes=mes2conn, routing_key=f"prs2conn.{conn_id}")

        self._logger.info(f"{self._config.svc_name} :: Сообщение об обновлении тега {tags} отправлено коннектору {conn_id}.")

    async def _tags_unlinked(self, mes: dict, routing_key: str | None = None):
        tags = mes["tagId"]
        if isinstance(tags, str):
            tags = [tags]
        conn_id = mes["connectorId"]
        mes2conn = {
            "action": "prsConnector.tags_deleted",
            "data": {"tags": tags}
        }

        await self._post_message(mes=mes2conn, routing_key=f"prs2conn.{conn_id}")
        self._logger.info(f"{self._config.svc_name} :: Сообщение об отвязке тега {tags} отправлено коннектору {conn_id}.")

    async def _tag_deleted(self, mes: dict, routing_key: str | None = None):
        # сервис prsConnector.model сам ищет привязки тега к коннекторам
        # и для каждого посылает сообщение, поэтому здесь не ищем список привязки тега

        tag_id = mes["tagId"]
        conn_id = mes["connectorId"]
        mes2conn = {
            "action": "prsConnector.tags_deleted",
            "data": {"tags": [tag_id]}
        }

        await self._post_message(mes=mes2conn, routing_key=f"prs2conn.{conn_id}")
        self._logger.info(f"{self._config.svc_name} :: Сообщение об удалении тега {tag_id} отправлено коннектору {conn_id}.")

    async def _get_tag_data(self, conn_id: str, tag_id: str) -> dict | None:
        # метод возвращает данные по тегу, привязанному к коннектору
        payload = {
            "base": conn_id,
            "filter": {
                "cn": [tag_id]
            },
            "attributes": ["prsJsonConfigString"]
        }
        link_res = await self._hierarchy.search(payload=payload)
        if not link_res:
            self._logger.error(f"{self._config.svc_name} :: В списке привязанных к коннектору {conn_id} не найден тег {tag_id}.")
            return None

        payload = {
            "id": tag_id,
            "attributes": ["prsValueTypeCode", "prsActive"]
        }
        tag_res = await self._hierarchy.search(payload=payload)
        if not tag_res:
            self._logger.error(f"{self._config.svc_name} :: К коннектору {conn_id} привязан несуществующий тег {tag_id}.")
            return None

        return {
            "prsActive": tag_res[0][2]["prsActive"][0] == 'TRUE',
            "prsValueTypeCode": int(tag_res[0][2]["prsValueTypeCode"][0]),
            "prsJsonConfigString": json.loads(link_res[0][2]["prsJsonConfigString"][0])
        }

    async def _get_connector_data(self, conn_id: str) -> dict:
        payload = {
            "id": conn_id,
            "attributes": ["prsActive", "prsEntityTypeCode", "prsJsonConfigString"]
        }
        res = await self._hierarchy.search(payload=payload)
        if not res:
            return {}
        return {
            "prsActive": res[0][2]["prsActive"][0] == 'TRUE',
            "prsEntityTypeCode": res[0][2]["prsEntityTypeCode"][0],
            "prsJsonConfigString": json.loads(
                res[0][2]["prsJsonConfigString"][0]
            )
        }

    async def _send_config_to_connector(self, mes: dict, routing_key: str | None = None) -> dict:

        conn_id = mes["data"]["id"]
        res = await self._get_connector_data(conn_id=conn_id)
        if not res:
            self._logger.error(f"{self._config.svc_name} :: Отсутствует коннектор {conn_id}.")
            return {}

        res["tags"] = {}
        mes_for_connector = {
            "action": "prsConnector.full_configuration",
            "data": res
        }

        tags = await self._hierarchy.search(payload={
            "base": conn_id,
            "scope": hierarchy.CN_SCOPE_SUBTREE,
            "filter": {
                "objectClass": ["prsConnectorTagData"]
            },
            "attributes": [
                "cn", "prsJsonConfigString"
            ]
        })

        for _, _, attrs in tags:
            tag_id = attrs["cn"][0]
            mes_for_connector["data"]["tags"][tag_id] = await self._get_tag_data(conn_id=conn_id, tag_id=tag_id)

        await self._post_message(mes=mes_for_connector, routing_key=f"prs2conn.{conn_id}")

        self._logger.info(f"{self._config.svc_name} :: Отправлена полная конфигурация коннектору {conn_id}.")
        return {}

    async def on_startup(self) -> None:

        await super().on_startup()

        try:
            payload = {}
            if self._config.nodes: # type: ignore
                payload["id"] = self._config.nodes # type: ignore
                for conn_id in self._config.nodes:
                    await self._bind_conn(conn_id=conn_id, bind=True)
            else:
                await self._bind_conn(conn_id="*", bind=True)
        except Exception as ex:
            self._logger.error(f"{self._config.svc_name} :: Ошибка инициализации сервиса коннекторов: {ex}")

    async def _bind_conn(self, conn_id: str, bind: bool = True):
        func = (self._amqp_consume_queue.unbind, self._amqp_consume_queue.bind)[bind]
        await self._amqp_consume_queue.bind(exchange=self._exchange, routing_key=f"prsConnector.model.link_tag.{conn_id}")
        await self._amqp_consume_queue.bind(exchange=self._exchange, routing_key=f"prsConnector.model.tag_link_updated.{conn_id}")
        await self._amqp_consume_queue.bind(exchange=self._exchange, routing_key=f"prsConnector.model.unlink_tag.{conn_id}")
        await self._amqp_consume_queue.bind(exchange=self._exchange, routing_key=f"prsConnector.model.tag_updated.{conn_id}")
        await self._amqp_consume_queue.bind(exchange=self._exchange, routing_key=f"prsConnector.model.tag_deleted.{conn_id}")
        await self._amqp_consume_queue.bind(exchange=self._exchange, routing_key=f"prsConnector.model.updated.{conn_id}")
        await self._amqp_consume_queue.bind(exchange=self._exchange, routing_key=f"prsConnector.model.deleted.{conn_id}")
        self._logger.info(f"{self._config.svc_name} :: Коннектор {conn_id} {('от', 'при')[bind]}вязан.")

    async def _deleting(self, mes: dict, routing_key: str | None = None):
        # удаление коннектора из модели:
        # делаем полную отвязку по этому коннектору
        conn_id = mes["id"]
        await self._bind_conn(conn_id, False)
        return {"response": True}

    async def _deleted(self, mes: dict, routing_key: str | None = None):
        deleted_conn_id = mes["id"]
        payload = {
            "action": "prsConnector.deleted",
            "data": {
                "id": deleted_conn_id
            }
        }
        await self._post_message(mes=payload, routing_key=f"prs2conn.{deleted_conn_id}")

        return {"response": True}

    async def _updated(self, mes: dict, routing_key: str | None = None):
        conn_id = mes["id"]
        res = await self._get_connector_data(conn_id=conn_id)
        if not res:
            self._logger.error(f"{self._config.svc_name} :: Отсутствует коннектор {conn_id}.")
            return {}

        mes_for_connector = {
            "action": "prsConnector.connector_configuration",
            "data": res
        }
        await self._post_message(mes=mes_for_connector, routing_key=f"prs2conn.{conn_id}")
        self._logger.info(f"{self._config.svc_name} :: Отправлена конфигурация коннектору {conn_id}.")

        return {"response": True}

settings = ConnectorsMQTTAppSettings()

app = ConnectorsMQTTApp(settings=settings, title="ConnectorsApp")
