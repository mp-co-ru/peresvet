import sys
import copy
import json

sys.path.append(".")

from src.common import model_crud_svc
from src.common import hierarchy
from src.services.connectors.model_crud.connectors_model_crud_settings import ConnectorsModelCRUDSettings

class ConnectorsModelCRUD(model_crud_svc.ModelCRUDSvc):
    """Сервис работы с коннекторами в иерархии.

<<<<<<< HEAD
    Подписывается на очередь ``connectors_api_crud`` обменника ``connectors_api_crud``\,
=======
    Подписывается на очередь ``connectors_api_crud`` обменника ``connectors_api_crud``,
>>>>>>> peresvet/dev
    в которую публикует сообщения сервис ``connectors_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: ConnectorsModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

<<<<<<< HEAD
    def _set_handlers(self) -> dict:
        return {
            "connectors.create": self._create,
            "connectors.read": self._read,
            "connectors.update": self._update,
            "connectors.delete": self._delete,
        }

    '''
    async def _further_read(self, mes: dict) -> dict:
        pass
    '''
=======
    def _set_handlers(self):
        super()._set_handlers()
        self._handlers["prsTag.model.updated.*"] = self._tag_updated
        self._handlers["prsTag.model.deleted.*"] = self._tag_deleted

    async def on_startup(self) -> None:

        await super().on_startup()

        # привяжемся к сообщениям по тегам
        payload = {
            "filter": {
                "objectClass": ["prsConnectorTagData"]
            },
            "attributes": ["cn"]
        }
        res = await self._hierarchy.search(payload=payload)
        if not res:
            self._logger.info("Нет привязанных к коннекторам тегов.")
            return
        tags = [tag_link[2]["cn"][0] for tag_link in res]
        tags_set = set(tags)
        for tag in tags_set:
            await self._amqp_consume_queue.bind(
                self._exchange,
                routing_key=f"prsTag.model.updated.{tag}")
            await self._amqp_consume_queue.bind(
                self._exchange,
                routing_key=f"prsTag.model.deleted.{tag}")

    async def _find_connector_by_tag(self, tag_id: str) -> list[str]:
        payload = {
            "base": "cn=connectors,cn=prs",
            "scope": hierarchy.CN_SCOPE_ONELEVEL,
            "filter": {"objectClass": ["prsConnector"]}
        }
        res = await self._hierarchy.search(payload)
        connectors = [res_item[0] for res_item in res]

        if not connectors:
            return []

        result = []
        for conn_id in connectors:
            payload = {"base": conn_id, "filter": {"cn": [tag_id]}}
            res = await self._hierarchy.search(payload)
            if res:
                result.append(conn_id)
        return result

    async def _tag_updated(self, mes: dict, routing_key: str | None = None) -> dict:
        mes_to_app = {
            "tagId": mes["id"]
        }

        connectors = await self._find_connector_by_tag(mes['id'])
        for conn_id in connectors:
            mes_to_app["connectorId"] = conn_id
            await self._post_message(
                mes=mes_to_app,
                routing_key=f"{self._config.hierarchy['class']}.model.tag_updated.{conn_id}")

        return {}

    async def _tag_deleted(self, mes: dict, routing_key: str | None = None) -> dict:
        mes_to_app = {
            "tagId": mes["id"]
        }

        await self._amqp_consume_queue.unbind(
            self._exchange, routing_key=f"prsTag.model.deleted.{mes_to_app['tagId']}"
        )
        await self._amqp_consume_queue.unbind(
            self._exchange, routing_key=f"prsTag.model.updated.{mes_to_app['tagId']}"
        )

        connectors = await self._find_connector_by_tag(mes['id'])
        for conn_id in connectors:
            mes_to_app["connectorId"] = conn_id
            await self._post_message(
                mes=mes_to_app,
                routing_key=f"{self._config.hierarchy['class']}.model.tag_deleted.{conn_id}")
            payload = {
                "base": conn_id,
                "filter": {
                    "cn": [mes_to_app["tagId"]],
                    "objectClass": ["prsConnectorTagData"]
                }
            }

            res = await self._hierarchy.search(payload=payload)
            if res:
                await self._hierarchy.delete(node=res[0][0])
                self._logger.info(f"Удалённый тег {mes_to_app['tagId']} отвязан от коннектора {conn_id}.")

        return {}
>>>>>>> peresvet/dev

    async def _further_create(self, mes: dict, new_id: str) -> None:
        sys_ids = await self._hierarchy.search(payload={
            "base": new_id,
            "scope": hierarchy.CN_SCOPE_ONELEVEL,
            "filter": {
                "cn": ["system"]
            }
        })
        sys_id = sys_ids[0][0]

        await self._hierarchy.add(sys_id, {"cn": "tags"})

<<<<<<< HEAD
        for item in mes["data"]["linkTags"]:
=======
        tags = mes.get("linkTags", [])
        for item in tags:
>>>>>>> peresvet/dev
            copy_item = copy.deepcopy(item)
            copy_item["connectorId"] = new_id
            await self._link_tag(copy_item)

    async def _further_update(self, mes: dict) -> None:

<<<<<<< HEAD
        cs_id = mes["data"]["id"]
        for item in mes["data"]["linkTags"]:
            copy_item = copy.deepcopy(item)
            copy_item["connectorId"] = cs_id
            await self._link_tag(copy_item)

    async def _link_tag(self, payload: dict) -> None:
=======
        conn_id = mes["id"]

        tags = mes.get("linkTags", [])

        linked_tags = []
        updated_links = []

        for item in tags:
            copy_item = copy.deepcopy(item)
            copy_item["connectorId"] = conn_id
            match await self._link_tag(copy_item):
                case self._TAG_LINKED:
                    linked_tags.append(item["tagId"])
                case self._TAG_LINK_UPDATED:
                    updated_links.append(item["tagId"])
        if linked_tags:
            await self._post_message(
                mes={"tagId": linked_tags, "connectorId": conn_id},
                routing_key=f"{self._config.hierarchy['class']}.model.link_tag.{conn_id}"
            )

        if updated_links:
            await self._post_message(
                mes={"tagId": updated_links, "connectorId": conn_id},
                routing_key=f"{self._config.hierarchy['class']}.model.tag_link_updated.{conn_id}"
            )

        tags = mes.get("unlinkTags", [])
        for tag_id in tags:
            await self._unlink_tag(conn_id, tag_id)
        if tags:
            await self._post_message(
                mes={"tagId": tags, "connectorId": conn_id},
                routing_key=f"{self._config.hierarchy['class']}.model.unlink_tag.{conn_id}"
            )

    async def _unlink_tag(self, conn_id: str, tag_id: str) -> None:
        payload = {
            "base": conn_id,
            "filter": {
                "cn": [tag_id]
            }
        }
        res = await self._hierarchy.search(payload=payload)
        if res:
            await self._hierarchy.delete(res[0][0])

            await self._amqp_consume_queue.unbind(
                self._exchange, routing_key=f"prsTag.model.deleted.{tag_id}"
            )
            await self._amqp_consume_queue.unbind(
                self._exchange, routing_key=f"prsTag.model.updated.{tag_id}"
            )

            self._logger.info(f"{self._config.svc_name} :: Коннектор {conn_id}. Тег {tag_id} отвязан.")

    _NO_TAG = 0
    _TAG_LINKED = 1
    _TAG_LINK_UPDATED = 2

    async def _link_tag(self, payload: dict) -> int:
>>>>>>> peresvet/dev
        """Метод привязки тега к коннектору.

        Метод создаёт новый узел в списке тегов коннектора.

        Args:
            payload (dict): {
                "tagId": "tag_id",
                "connectorId": "conn_id",
                "attributes": {
                    "prsJsonConfigString":
                }
            }
<<<<<<< HEAD
        """
        """
=======
>>>>>>> peresvet/dev
        res = await self._post_message(
            mes={"action": "connectors.linkTag", "data": payload},
            reply=True,
            routing_key=payload["connectorId"])

        prs_store = res.get("prsJsonConfigString")
<<<<<<< HEAD
=======

        Возвращает:
        0 - нет указанного тега в иерархии
        1 - тег привязан
        2 - тег уже был привязан, обновлена привязка
>>>>>>> peresvet/dev
        """

        node_dn = await self._hierarchy.get_node_dn(payload['connectorId'])
        tags_node_id = await self._hierarchy.get_node_id(
            f"cn=tags,cn=system,{node_dn}"
        )
<<<<<<< HEAD
=======

        search = {
            "id": payload["tagId"],
            "attributes": ["cn"]
        }
        res = await self._hierarchy.search(search)
        if not res:
            self._logger.error(f"Попытка привязки к коннектору несуществующего тега {payload['tagId']}")
            return self._NO_TAG


        # может, данный тег уже привязан
        tag_src = {
            "base": tags_node_id,
            "filter": {
                "cn": [payload["tagId"]]
            },
            "attributes": ["cn"]
        }
        res = await self._hierarchy.search(payload=tag_src)
        if res:
            await self._hierarchy.modify(
                res[0][0],
                {
                    "prsJsonConfigString": payload["attributes"]["prsJsonConfigString"],
                    "description": payload["attributes"].get("description")
                })

            self._logger.info(f"{self._config.svc_name} :: Коннектор {payload['connectorId']}. Изменена привязка тега {payload['tagId']}.")
            return self._TAG_LINK_UPDATED

>>>>>>> peresvet/dev
        new_node_id = await self._hierarchy.add(
            base=tags_node_id,
            attribute_values={
                "objectClass": ["prsConnectorTagData"],
                "cn": payload["tagId"],
                "prsJsonConfigString": payload["attributes"]["prsJsonConfigString"],
<<<<<<< HEAD
                "prsValueScale": payload["attributes"]["prsValueScale"],
                "prsMaxDev": payload["attributes"]["prsMaxDev"],
                "description": payload["attributes"]["description"]
=======
                "description": payload["attributes"].get("description")
>>>>>>> peresvet/dev
            }
        )
        await self._hierarchy.add_alias(
            parent_id=new_node_id,
            aliased_object_id=payload["tagId"],
            alias_name=payload["tagId"]
        )

<<<<<<< HEAD
=======
        await self._amqp_consume_queue.bind(
            self._exchange,
            routing_key=f"prsTag.model.updated.{payload['tagId']}")
        await self._amqp_consume_queue.bind(
            self._exchange,
            routing_key=f"prsTag.model.deleted.{payload['tagId']}")

>>>>>>> peresvet/dev
        self._logger.info(
            f"{self._config.svc_name} :: Тег {payload['tagId']} привязан к коннектору {payload['connectorId']}"
        )

<<<<<<< HEAD
    async def _further_read(self, mes: dict, search_result: dict) -> dict:

        if not mes["data"]["getLinkedTags"]:
=======
        return self._TAG_LINKED

    async def _further_read(self, mes: dict, search_result: dict) -> dict:

        if not mes["getLinkedTags"]:
>>>>>>> peresvet/dev
            return search_result

        res = {"data": []}
        for connector in search_result["data"]:
            conn_id = connector["id"]
            new_conn = copy.deepcopy(connector)
            new_conn["linkedTags"] = []
            items = await self._hierarchy.search(
                {
                    "base": conn_id,
                    "filter": {
                        "objectClass": ["prsConnectorTagData"]
                    },
<<<<<<< HEAD
                    "attributes": ["cn", "prsJsonConfigString", "prsMaxDev", "prsValueScale"],
=======
                    "attributes": ["cn", "prsJsonConfigString"],
>>>>>>> peresvet/dev
                    "scope": 2
                }
            )
            if items:
                for item in items:
                    new_conn["linkedTags"].append(
                        {
                            "tagId": item[2]["cn"][0],
                            "attributes": {
                                "cn": item[2]["cn"][0],
                                "prsJsonConfigString": json.loads(item[2]["prsJsonConfigString"][0]),
<<<<<<< HEAD
                                "prsMaxDev": item[2]["prsMaxDev"][0],
                                "prsValueScale": item[2]["prsValueScale"][0],
=======
>>>>>>> peresvet/dev
                                "objectClass": "prsConnectorTagData"
                            }
                        }
                    )

            res["data"].append(new_conn)

        return res


settings = ConnectorsModelCRUDSettings()

app = ConnectorsModelCRUD(settings=settings, title="ConnectorsModelCRUD")
