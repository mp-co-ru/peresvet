import sys
import copy

sys.path.append(".")

from consts_model_crud_settings import ConstsModelCRUDSettings
from src.common import model_crud_svc
from src.common import hierarchy

class ConstsModelCRUD(model_crud_svc.ModelCRUDSvc):
    """Сервис работы с константами в иерархии.

    Подписывается на очередь ``consts_api_crud`` обменника ``consts_api_crud``,
    в которую публикует сообщения сервис ``consts_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: ConstsModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def _reading(self, mes: dict) -> dict:
        pass

    async def _creating(self, mes: dict, new_id: str) -> None:
        pass

settings = ConstsModelCRUDSettings()

app = ConstsModelCRUD(settings=settings, title="ConstsModelCRUD")
