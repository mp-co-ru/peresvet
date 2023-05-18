import copy
import src.common.model_crud_svc as model_crud
import src.common.hierarchy as hierarchy
from .tags_model_crud_settings import TagsModelCRUDSettings

class TagsModelCRUD(model_crud.ModelCRUDSvc):
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
                res = self._hierarchy.search({
                    "base": self._system_node_id,
                    "deref": True,
                    "scope": hierarchy.CN_SCOPE_ONELEVEL,
                    "filter": {
                        "objectClass": "prsDataStorage"
                    },
                    "attributes": ["cn"]
                })
                if res:
                    new_item["dataStorageId"] = res[0][0]

            if mes["getDataSourceId"]:
                res = self._hierarchy.search({
                    "base": self._system_node_id,
                    "deref": True,
                    "scope": hierarchy.CN_SCOPE_ONELEVEL,
                    "filter": {
                        "objectClass": "prsDataSource"
                    },
                    "attributes": ["cn"]
                })
                if res:
                    new_item["dataSourceId"] = res[0][0]

            new_res["data"].append(new_item)

        return new_res

    #TODO: creating for dataStorage and dataSource
    async def _creating(self, mes: dict, new_id: str) -> None:
        system_node_id = await self._hierarchy.search(payload={
            "base": new_id,
            "scope": hierarchy.CN_SCOPE_ONELEVEL,
            "filter": {
                "cn": ["system"]
            }
        })

        if mes["data"]["dataStorageId"]:
            pass
        if mes["data"]["dataSourceId"]:
            pass
