import sys
import copy

sys.path.append(".")

from dataStorages_model_crud_settings import DataStoragesModelCRUDSettings
from src.common import model_crud_svc
from src.common import hierarchy

class DataStoragesModelCRUD(model_crud_svc.ModelCRUDSvc):
    """Сервис работы с хранилищами данных в иерархии.

    Подписывается на очередь ``dataStorages_api_crud`` обменника ``dataStorages_api_crud``,
    в которую публикует сообщения сервис ``dataStorages_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: DataStoragesModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def _reading(self, mes: dict) -> dict:
        pass

    async def _link_tag(payload: dict) -> None:
        """Метод привязки тега к хранилищу.

        Args:
            payload (dict): {
                "id": "tag_id",
                "attributes": {
                    "prsStore":
                }
            }
        """


    async def _link_alert(payload: dict) -> None:
        pass

    async def _creating(self, mes: dict, new_id: str) -> None:
        sys_id = await anext(self._hierarchy.search({
            "base": new_id,
            "scope": hierarchy.CN_SCOPE_ONELEVEL,
            "filter": {
                "cn": ["system"]
            }
        }))

        sys_id = sys_id[0]

        await self._hierarchy.add(sys_id, {"cn": "tags"})
        await self._hierarchy.add(sys_id, {"cn": "alerts"})

        for item in mes["data"]["linkTags"]:
            await self._link_tag(item)
        for item in mes["data"]["linkAlerts"]:
            await self._link_alert(item)

settings = DataStoragesModelCRUDSettings()

app = DataStoragesModelCRUD(settings=settings, title="DataStoragesModelCRUD")
