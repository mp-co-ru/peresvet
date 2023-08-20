import sys
import copy

sys.path.append(".")

from connectors_model_crud_settings import ConnectorsModelCRUDSettings
from src.common import model_crud_svc
from src.common import hierarchy

class ConnectorsModelCRUD(model_crud_svc.ModelCRUDSvc):
    """Сервис работы с коннекторами в иерархии.

    Подписывается на очередь ``connectors_api_crud`` обменника ``connectors_api_crud``,
    в которую публикует сообщения сервис ``connectors_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    _outgoing_commands = {
        "created": "connectors.created",
        "mayUpdate": "connectors.mayUpdate",
        "updating": "connectors.updating",
        "updated": "connectors.updated",
<<<<<<< HEAD
        "mayDelete": "connectors.mayDelete",
=======
        "mayDelete": "connetors.mayDelete",
>>>>>>> d2074789837efdb871ee581824524cdc755f4ef1
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

<<<<<<< HEAD
    async def _further_read(self, mes: dict) -> dict:
=======
    async def _reading(self, mes: dict) -> dict:
>>>>>>> d2074789837efdb871ee581824524cdc755f4ef1
        pass

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

        linkTags = mes.get('data').get('linkTags')
        self._logger.info(linkTags)

        if linkTags and isinstance(linkTags, list):
            for linkTag in linkTags:
                prsSource = linkTag.get('attributes').get('prsSource')
                prsMaxDev = linkTag.get('attributes').get('prsMaxDev')
                prsValueScale = linkTag.get('attributes').get('prsValueScale')
                prs_connector_tag_data_id = await self._hierarchy.add(system_node_id, 
                                                                    {"objectClass": ["prsConnectorTagData"],
                                                                     "cn": [linkTag.get('id')],
                                                                    "prsSource": prsSource,
                                                                    "prsMaxDev": prsMaxDev,
                                                                    "prsValueScale": prsValueScale})
                await self._hierarchy.add_alias(
                    prs_connector_tag_data_id, linkTag.get('id'), linkTag.get('id')
                )

settings = ConnectorsModelCRUDSettings()

app = ConnectorsModelCRUD(settings=settings, title="ConnectorsModelCRUD")
