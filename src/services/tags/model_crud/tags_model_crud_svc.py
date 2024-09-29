import sys
import copy

sys.path.append(".")

from src.common import model_crud_svc
from src.common import hierarchy
from src.services.tags.model_crud.tags_model_crud_settings import TagsModelCRUDSettings

class TagsModelCRUD(model_crud_svc.ModelCRUDSvc):
    """Сервис работы с тегами в иерархии.

    Подписывается на очередь ``tags_api_crud`` обменника ``tags_api_crud``\,
    в которую публикует сообщения сервис ``tags_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: TagsModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def _further_create(self, mes: dict, new_id: str) -> None:
        system_node = await self._hierarchy.search(payload={
            "base": new_id,
            "scope": hierarchy.CN_SCOPE_ONELEVEL,
            "filter": {
                "cn": ["system"]
            },
            "attributes": ["cn"]
        })
        if not system_node:
            self._logger.error(f"В теге {new_id} отсутствует узел `system`.")
            return

        system_node_id = system_node[0][0]

        if mes.get("dataStorageId"):
            await self._hierarchy.add_alias(
                system_node_id, mes["data"]["dataStorageId"], "dataStorage"
            )

        if mes.get("connectorId"):
            await self._hierarchy.add_alias(
                system_node_id, mes["connectorId"], "connector"
            )

settings = TagsModelCRUDSettings()

app = TagsModelCRUD(settings=settings, title="TagsModelCRUD")
