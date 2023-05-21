import sys
import copy

sys.path.append(".")

from tags_model_crud_settings import TagsModelCRUDSettings
from src.common import model_crud_svc
from src.common import hierarchy

class TagsModelCRUD(model_crud_svc.ModelCRUDSvc):
    """Сервис работы с тегами в иерархии.

    Подписывается на очередь ``tags_api_crud`` обменника ``tags_api_crud``,
    в которую публикует сообщения сервис ``tags_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: TagsModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def _reading(self, mes: dict, search_result: dict) -> dict:
        """Чтение дополнительных параметров для тега: id хранилища данных
        и источника данных.
        """
        new_res = {"data": []}
        for item in search_result["data"]:
            new_item = copy.deepcopy(item)

            if mes["getDataStorageId"]:
                res = await anext(self._hierarchy.search({
                    "base": self._system_node_id,
                    "deref": True,
                    "scope": hierarchy.CN_SCOPE_ONELEVEL,
                    "filter": {
                        "objectClass": "prsDataStorage"
                    },
                    "attributes": ["cn"]
                }))

                if res:
                    new_item["dataStorageId"] = res[0][0]
                else:
                    new_item["dataStorageId"] = None

            if mes.get("getConnectorId"):
                res = await anext(self._hierarchy.search({
                    "base": self._system_node_id,
                    "deref": True,
                    "scope": hierarchy.CN_SCOPE_ONELEVEL,
                    "filter": {
                        "objectClass": "prsConnector"
                    },
                    "attributes": ["cn"]
                }))

                if res:
                    new_item["connectorId"] = res[0][0]
                else:
                    new_item["connectorId"] = None

            new_res["data"].append(new_item)

        return new_res

    async def _creating(self, mes: dict, new_id: str) -> None:
        system_node = await anext(self._hierarchy.search(payload={
            "base": new_id,
            "scope": hierarchy.CN_SCOPE_ONELEVEL,
            "filter": {
                "cn": ["system"]
            },
            "attributes": ["cn"]
        }))
        if not system_node:
            self._logger.error(f"В теге {new_id} отсутствует узел `system`.")
            return

        system_node_id = system_node[0]

        if mes["data"].get("dataStorageId"):
            await self._hierarchy.add_alias(
                system_node_id, mes["data"]["dataStorageId"], "dataStorage"
            )


        if mes["data"].get("connectorId"):
            await self._hierarchy.add_alias(
                system_node_id, mes["data"]["connectorId"], "connector"
            )

settings = TagsModelCRUDSettings()

app = TagsModelCRUD(settings=settings, title="TagsModelCRUD")
