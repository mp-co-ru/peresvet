import sys
import copy
import json

sys.path.append(".")

from src.common import model_crud_svc
from src.common import hierarchy
from src.services.connectors.model_crud.connectors_model_crud_settings import ConnectorsModelCRUDSettings

class ConnectorsModelCRUD(model_crud_svc.ModelCRUDSvc):
    """Сервис работы с коннекторами в иерархии.

    Подписывается на очередь ``connectors_api_crud`` обменника ``connectors_api_crud``,
    в которую публикует сообщения сервис ``connectors_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: ConnectorsModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

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

        tags = mes.get("linkTags", [])
        for item in tags:
            copy_item = copy.deepcopy(item)
            copy_item["connectorId"] = new_id
            await self._link_tag(copy_item)

    async def _further_update(self, mes: dict) -> None:

        conn_id = mes["id"]

        tags = mes.get("linkTags", [])

        for item in tags:
            copy_item = copy.deepcopy(item)
            copy_item["connectorId"] = conn_id
            await self._link_tag(copy_item)

        tags = mes.get("unlinkTags", [])
        for tag_id in tags:
            await self._unlink_tag(conn_id, tag_id)

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

            await self._post_message(
                mes={"tagId": tag_id},
                routing_key=f"{self._config.hierarchy['class']}.model.unlink_tag.{conn_id}"
            )
            self._logger.info(f"{self._config.svc_name} :: Коннектор {conn_id}. Тег {tag_id} отвязан.")

    async def _link_tag(self, payload: dict) -> None:
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
        res = await self._post_message(
            mes={"action": "connectors.linkTag", "data": payload},
            reply=True,
            routing_key=payload["connectorId"])

        prs_store = res.get("prsJsonConfigString")
        """

        node_dn = await self._hierarchy.get_node_dn(payload['connectorId'])
        tags_node_id = await self._hierarchy.get_node_id(
            f"cn=tags,cn=system,{node_dn}"
        )

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

            await self._post_message(
                mes={"tagId": payload["tagId"]},
                routing_key=f"{self._config.hierarchy['class']}.model.linked_tag_updated.{payload['connectorId']}"
            )
            self._logger.info(f"{self._config.svc_name} :: Коннектор {payload['connectorId']}. Изменена привязка тега {payload['tagId']}.")
            return

        new_node_id = await self._hierarchy.add(
            base=tags_node_id,
            attribute_values={
                "objectClass": ["prsConnectorTagData"],
                "cn": payload["tagId"],
                "prsJsonConfigString": payload["attributes"]["prsJsonConfigString"],
                "description": payload["attributes"].get("description")
            }
        )
        await self._hierarchy.add_alias(
            parent_id=new_node_id,
            aliased_object_id=payload["tagId"],
            alias_name=payload["tagId"]
        )

        await self._post_message(
                mes={"tagId": payload["tagId"]},
                routing_key=f"{self._config.hierarchy['class']}.model.link_tag.{payload['connectorId']}"
            )

        self._logger.info(
            f"{self._config.svc_name} :: Тег {payload['tagId']} привязан к коннектору {payload['connectorId']}"
        )

    async def _further_read(self, mes: dict, search_result: dict) -> dict:

        if not mes["getLinkedTags"]:
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
                    "attributes": ["cn", "prsJsonConfigString"],
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
                                "objectClass": "prsConnectorTagData"
                            }
                        }
                    )

            res["data"].append(new_conn)

        return res


settings = ConnectorsModelCRUDSettings()

app = ConnectorsModelCRUD(settings=settings, title="ConnectorsModelCRUD")
