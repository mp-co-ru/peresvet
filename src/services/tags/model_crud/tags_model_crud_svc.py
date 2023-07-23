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

    _outgoing_commands = {
        "created": "tags.created",
        "mayUpdate": "tags.mayUpdate",
        "updating": "tags.updating",
        "updated": "tags.updated",
        "mayDelete": "tags.mayDelete",
        "deleting": "tags.deleting",
        "deleted": "tags.deleted"
    }

    def __init__(self, settings: TagsModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    def _set_incoming_commands(self) -> dict:
        return {
            "tags.create": self._create,
            "tags.read": self._read,
            "tags.update": self._update,
            "tags.delete": self._delete,
        }

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
