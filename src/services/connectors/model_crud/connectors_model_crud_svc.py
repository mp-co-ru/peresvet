import sys
import copy
import json

sys.path.append(".")

from src.common import model_crud_svc
from src.common import hierarchy
from src.services.connectors.model_crud.connectors_model_crud_settings import ConnectorsModelCRUDSettings

class ConnectorsModelCRUD(model_crud_svc.ModelCRUDSvc):
    """Сервис работы с коннекторами в иерархии.

    Подписывается на очередь ``connectors_api_crud`` обменника ``connectors_api_crud``\,
    в которую публикует сообщения сервис ``connectors_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: ConnectorsModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

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

        for item in mes["data"]["linkTags"]:
            copy_item = copy.deepcopy(item)
            copy_item["connectorId"] = new_id
            await self._link_tag(copy_item)

    async def _further_update(self, mes: dict) -> None:

        cs_id = mes["data"]["id"]
        for item in mes["data"]["linkTags"]:
            copy_item = copy.deepcopy(item)
            copy_item["connectorId"] = cs_id
            await self._link_tag(copy_item)

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
        """
        """
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
        new_node_id = await self._hierarchy.add(
            base=tags_node_id,
            attribute_values={
                "objectClass": ["prsConnectorTagData"],
                "cn": payload["tagId"],
                "prsJsonConfigString": payload["attributes"]["prsJsonConfigString"],
                "prsValueScale": payload["attributes"]["prsValueScale"],
                "prsMaxDev": payload["attributes"]["prsMaxDev"],
                "description": payload["attributes"]["description"]
            }
        )
        await self._hierarchy.add_alias(
            parent_id=new_node_id,
            aliased_object_id=payload["tagId"],
            alias_name=payload["tagId"]
        )

        self._logger.info(
            f"{self._config.svc_name} :: Тег {payload['tagId']} привязан к коннектору {payload['connectorId']}"
        )

    async def _further_read(self, mes: dict, search_result: dict) -> dict:

        if not mes["data"]["getLinkedTags"]:
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
                    "attributes": ["cn", "prsJsonConfigString", "prsMaxDev", "prsValueScale"],
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
                                "prsMaxDev": item[2]["prsMaxDev"][0],
                                "prsValueScale": item[2]["prsValueScale"][0],
                                "objectClass": "prsConnectorTagData"
                            }
                        }
                    )

            res["data"].append(new_conn)

        return res


settings = ConnectorsModelCRUDSettings()

app = ConnectorsModelCRUD(settings=settings, title="ConnectorsModelCRUD")
