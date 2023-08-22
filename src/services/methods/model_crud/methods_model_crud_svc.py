import sys
import copy

sys.path.append(".")

from src.services.methods.model_crud.methods_model_crud_settings import MethodsModelCRUDSettings
from src.common import model_crud_svc
from src.common import hierarchy

class MethodsModelCRUD(model_crud_svc.ModelCRUDSvc):
    """Сервис работы с тегами в иерархии.

    Подписывается на очередь ``tags_api_crud`` обменника ``tags_api_crud``,
    в которую публикует сообщения сервис ``tags_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    _outgoing_commands = {
        "created": "methods.created",
        "mayUpdate": "methods.mayUpdate",
        "updating": "methods.updating",
        "updated": "methods.updated",
        "mayDelete": "methods.mayDelete",
        "deleting": "methods.deleting",
        "deleted": "methods.deleted"
    }

    def __init__(self, settings: MethodsModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    def _set_incoming_commands(self) -> dict:
        return {
            "methods.create": self._create,
            "methods.read": self._read,
            "methods.update": self._update,
            "methods.delete": self._delete,
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
            self._logger.error(f"В методе {new_id} отсутствует узел `system`.")
            return

        system_node_id = system_node[0][0]

        # создадим список инициаторов расчёта
        initiatedBy_node_id = await self._hierarchy.add(
            system_node_id,
            {"cn": ["initiatedBy"]}
        )
        for initiator_id in mes["data"]["initiatedBy"]:
            await self._hierarchy.add(
                initiatedBy_node_id,
                {"cn": [initiator_id]}
            )
        # создадим узлы-параметры
        parameters_node_id = await self._hierarchy.add(
            system_node_id,
            {"cn": ["parameters"]}
        )
        for parameter in mes["data"]["parameters"]:
            parameter["attributes"]["objectClass"] = ["prsMethodParameter"]
            await self._hierarchy.add(
                parameters_node_id,
                parameter["attributes"]
            )

settings = MethodsModelCRUDSettings()

app = MethodsModelCRUD(settings=settings, title="TagsModelCRUD")
