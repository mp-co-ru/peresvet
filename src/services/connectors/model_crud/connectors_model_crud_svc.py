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

    def __init__(self, settings: ConnectorsModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def _reading(self, mes: dict) -> dict:
        pass

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

        if mes["data"].get("linkTags"):
            linkTags = mes.get('data').get('linkTags')
            prsSource = mes.get('data').get('prsSource')
            prsMaxDev = mes.get('data').get('prsMaxDev')
            prsValueScale = mes.get('data').get('prsValueScale')
            prs_connector_tag_data_id = await self._hierarchy.add(system_node_id, 
                                                                  {"objectClass": ["prsConnectorTagData"],
                                                                   "prsSource": prsSource,
                                                                   "prsMaxDev": prsMaxDev,
                                                                   "prsValueScale": prsValueScale})
            # await self._hierarchy.add_alias(
            #     prs_connector_tag_data_id, mes["data"]["linkTags"], mes["data"]["linkTags"]
            # )

settings = ConnectorsModelCRUDSettings()

app = ConnectorsModelCRUD(settings=settings, title="ConnectorsModelCRUD")
