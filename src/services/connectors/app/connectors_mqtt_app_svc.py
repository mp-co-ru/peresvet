import sys
import json

from fastapi import APIRouter
import aio_pika
import aio_pika.abc
sys.path.append(".")

from src.services.connectors.app.connectors_app_mqtt_settings import ConnectorsMQTTAppSettings
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
        self._handlers["prsTag.model.updated.*"] = self._tag_updated
        self._handlers["prsTag.model.deleted.*"] = self._tag_deleted

    async def _find_connector_by_tag(self, tag_id: str) -> list[str]:
        if not self._config.nodes: # type: ignore
            payload = {"base": "cn=connectors,cn=prs", "scope": hierarchy.CN_SCOPE_ONELEVEL}
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

    async def _tag_updated(self, mes: dict, routing_key: str | None = None):
        # TODO: по правильному, чтобы получить данные по какой-либо сущности,
        # необходимо делать запрос соответствующему сервису,
        # но, так как система сообщений ещё не устоялась,
        # будем искать данные сразу в иерархии
        tag_id = mes["id"]

        # прочитаем данные самого тега ------------------------------------------
        payload = {
            "base": tag_id,
            "attributes" : ["prsActive", "prsValueTypeCode"]
        }
        res = await self._hierarchy.search(payload)
        if not res:
            self._logger.error(f"Обновление тега {tag_id}. Тег не найден.")
            return

        mes2conn = {
            "action": "prsConnector.tags_configuration",
            "data": {
                "tags": {
                    tag_id: {
                        "prsActive": res[0][2]["prsActive"] == 'TRUE',
                        "prsValueTypeCode": int(res[0][2]["prsValueTypeCode"][0])
                    }
                }
            }
        }
        # ---------------------------------------------------------------------

        # получаем список коннекторов, к которым привязан тег -----------------
        connectors = await self._find_connector_by_tag(tag_id)
        if not connectors:
            self._logger.error(f"Тег {tag_id} не привязан к коннектору.")
            return
        # --------------------------------------------------------------------

        payload = {
            "base": None,
            "filter": {"cn": [tag_id]},
            "attributes": ["prsJsonConfigString"]
        }
        for conn_id in connectors:
            # получим данные по привязке тега
            payload["base"] = conn_id
            res = await self._hierarchy.search(payload)
            if not res:
                self._logger.error(f"Ошибка поиска привязки тега {tag_id} к коннектору {conn_id}.")
                continue

            mes2conn["data"]["tags"][tag_id]["prsJsonConfigString"] = json.loads(res[0][2]["prsJsonConfigString"])
            await self._post_message(mes=mes2conn, routing_key=f"prs2conn.{conn_id}")

            self._logger.info(f"Сообщение об обновлении тега {tag_id} отправлено коннектору {conn_id}.")

    async def _tag_deleted(self, mes: dict, routing_key: str | None = None):
        tag_id = mes["id"]
        # получаем список коннекторов, к которым привязан тег -----------------
        connectors = await self._find_connector_by_tag(tag_id)
        if not connectors:
            self._logger.error(f"Тег {tag_id} не привязан к коннектору.")
            return
        # --------------------------------------------------------------------

        mes2conn = {
            "action": "prsConnector.tags_deleted",
            "data": {"tags": [tag_id]}
        }

        for conn_id in connectors:
            await self._post_message(mes=mes2conn, routing_key=f"prs2conn.{conn_id}")
            self._logger.info(f"Сообщение об удалении тега {tag_id} отправлено коннектору {conn_id}.")

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
            self._logger.error(f"В списке привязанных к коннектору {conn_id} не найден тег {tag_id}.")
            return None

        payload = {
            "id": tag_id,
            "attributes": ["prsValueTypeCode", "prsActive"]
        }
        tag_res = await self._hierarchy.search(payload=payload)
        if not tag_res:
            self._logger.error(f"К коннектору {conn_id} привязан несуществующий тег {tag_id}.")
            return None

        return {
            "prsActive": tag_res[0][2]["prsActive"][0] == 'TRUE',
            "prsValueTypeCode": int(tag_res[0][2]["prsValueTypeCode"][0]),
            "prsJsonConfigString": json.loads(link_res[0][2]["prsJsonConfigString"][0])
        }

    async def _send_config_to_connector(self, mes: dict, routing_key: str | None = None) -> dict:

        conn_id = mes["data"]["id"]
        payload = {
            "id": conn_id,
            "attributes": ["prsActive", "prsEntityTypeCode", "prsJsonConfigString"]
        }
        res = await self._hierarchy.search(payload=payload)
        if not res:
            self._logger.error(f"Отсутствует коннектор с id = {conn_id}.")
            return {}

        mes_for_connector = {
            "action": "prsConnector.full_configuration",
            "data": {
                "prsActive": res[0][2]["prsActive"][0] == 'TRUE',
                "prsEntityTypeCode": res[0][2]["prsEntityTypeCode"][0],
                "prsJsonConfigString": json.loads(
                    res[0][2]["prsJsonConfigString"][0]
                ),
                "tags": {}
            }
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

        for tag_id, _, _ in tags:
            mes_for_connector["tags"]["tag_id"] = self._get_tag_data(conn_id=conn_id, tag_id=tag_id)

        await self._post_message(mes=mes_for_connector, routing_key=f"prs2conn.{conn_id}")

        self._logger.info(f"Отправлена полная конфигурация коннектору {conn_id}.")
        return {}

    async def on_startup(self) -> None:

        await super().on_startup()

        # сделаем перепривязку очереди, так как слушать будем только нужные сообщения
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsTag.model.updated.*")
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsTag.model.deleted.*")
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsConnector.model.link_tag.*")
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsConnector.model.unlink_tag.*")
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsConnector.model.updated.*")
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsConnector.model.deleted.*")
        # ----------------------------------------------------------------------------------------

        try:
            payload = {}
            if self._config.nodes: # type: ignore
                payload["id"] = self._config.nodes # type: ignore
            else:
                conn_node_id = await self._hierarchy.get_node_id("cn=connectors,cn=prs")
                payload = {
                    "base": conn_node_id,
                    "filter": {
                        "objectClass": ["prsConnector"]
                    }
                }

            conns = await self._hierarchy.search(payload=payload)
            for conn in conns:
                await self._add_supported_conn(conn[0])

        except Exception as ex:
            self._logger.error(f"{self._config.svc_name} :: Ошибка инициализации сервиса коннекторов: {ex}")

    async def _bind_conn(self, conn_id: str, bind: bool = True):
        func = (self._amqp_consume_queue.unbind, self._amqp_consume_queue.bind)[bind]
        await func(exchange=self._exchange, routing_key=f"prsConnector.model.link_tag.{conn_id}")
        await func(exchange=self._exchange, routing_key=f"prsConnector.model.unlink_tag.{conn_id}")
        await func(exchange=self._exchange, routing_key=f"prsConnector.model.updated.{conn_id}")
        await func(exchange=self._exchange, routing_key=f"prsConnector.model.deleted.{conn_id}")
        await func(exchange=self._exchange, routing_key=f"conn2prs.{conn_id}")
        self._logger.info(f"Коннектор {conn_id} {('от', 'при')[bind]}вязан.")

    async def _add_supported_conn(self, conn_id: str) -> None:

        """Метод добавляет в список поддерживаемых коннекторов новый коннектор.

        Args:
            conn_id (str): идентификатор коннектора
        """
        payload = {
            "id": [conn_id],
            "attributes": ["prsJsonConfigString", "prsActive", "prsEntityTypeCode"]
        }
        conn = await self._hierarchy.search(payload=payload)

        # привяжемся к сообщениям, касающихся изменений коннектора ---------------------------------
        await self._bind_conn(conn_id, True)
        # ----------------------------------------------------------------------------------------
        if conn[0][2]["prsActive"][0] == "TRUE":
            await self._bind_all_tags(conn_id)

    async def _bind_all_tags(self, conn_id: str, bind: bool = True):
        payload = {
            "base": conn_id,
            "filter": {
                "objectClass": ["prsConnectorTagData"]
            },
            "attributes": ["cn"]
        }

        tags = await self._hierarchy.search(payload)
        for tag in tags:
            await self._bind_tag(tag[2]["cn"][0], bind)

    async def _bind_tag(self, tag_id: str, bind: bool = True) -> None:
        """
        Привязка тега для прослушивания.
        """
        func = (self._amqp_consume_queue.unbind, self._amqp_consume_queue.bind)[bind]
        await func(exchange=self._exchange, routing_key=f"prsTag.model.updated.{tag_id}")
        await func(exchange=self._exchange, routing_key=f"prsTag.model.deleted.{tag_id}")

    async def _deleting(self, mes: dict, routing_key: str | None = None):
        # удаление коннектора из модели:
        # делаем полную отвязку по этому коннектору
        conn_id = mes["id"]
        await self._bind_conn(conn_id, False)
        await self._bind_all_tags(conn_id, False)
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
        payload = {"data": {"id": mes["id"]}}
        await self._send_config_to_connector(mes=payload, routing_key=routing_key)
        return {"response": True}

settings = ConnectorsMQTTAppSettings()

app = ConnectorsMQTTApp(settings=settings, title="ConnectorsApp")
