import sys
import copy

sys.path.append(".")

from connectors_model_crud_settings import ConnectorsModelCRUDSettings
from src.common import model_crud_svc
from src.common import hierarchy

class ConnectorsModelCRUD(model_crud_svc.ModelCRUDSvc):
    """Сервис работы с коннекторами в иерархии.

    Подписывается на очередь ``connectors_api_crud`` обменника ``connectors_api_crud``\,
    в которую публикует сообщения сервис ``connectors_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    _outgoing_commands = {
        "created": "connectors.created",
        "mayUpdate": "connectors.mayUpdate",
        "updating": "connectors.updating",
        "updated": "connectors.updated",
        "mayDelete": "connetors.mayDelete",
        "deleting": "connectors.deleting",
        "deleted": "connectors.deleted"
    }

    def __init__(self, settings: ConnectorsModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    def _set_incoming_commands(self) -> dict:
        return {
            "connectors.create": self._create,
            "connectors.read": self._read,
            "connectors.update": self._update,
            "connectors.delete": self._delete,
        }

    async def _further_read(self, mes: dict) -> dict:
        pass

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

        ds_id = mes["data"]["id"]
        for item in mes["data"]["linkTags"]:
            copy_item = copy.deepcopy(item)
            copy_item["connectorId"] = ds_id
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
        res = await self._post_message(
            mes={"action": "connectors.linkTag", "data": payload},
            reply=True,
            routing_key=payload["connectorId"])

        prs_store = res.get("prsJsonConfigString")

        node_dn = await self._hierarchy.get_node_dn(payload['connectorId'])
        tags_node_id = await self._hierarchy.get_node_id(
            f"cn=tags,cn=system,{node_dn}"
        )
        new_node_id = await self._hierarchy.add(
            base=tags_node_id,
            attribute_values={
                "objectClass": ["prsConnectorTagData"],
                "cn": payload["tagId"],
                "prsJsonConfigString": prs_store
            }
        )
        await self._hierarchy.add_alias(
            parent_id=new_node_id,
            aliased_object_id=payload["tagId"],
            alias_name=payload["tagId"]
        )

        self._logger.info(
            f"Тег {payload['tagId']} привязан к коннектору {payload['connectorId']}"
        )

settings = ConnectorsModelCRUDSettings()

app = ConnectorsModelCRUD(settings=settings, title="ConnectorsModelCRUD")
