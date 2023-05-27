import sys
import copy

sys.path.append(".")

from constants_model_crud_settings import ConstantsModelCRUDSettings
from src.common import model_crud_svc
from src.common import hierarchy

class ConstantsModelCRUD(model_crud_svc.ModelCRUDSvc):
    """Сервис работы с константами в иерархии.

    Подписывается на очередь ``constants_api_crud`` обменника ``constants_api_crud``,
    в которую публикует сообщения сервис ``constants_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: ConstantsModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def _reading(self, mes: dict) -> dict:
        pass

    async def _creating(self, mes: dict, new_id: str) -> None:
        pass

settings = ConstantsModelCRUDSettings()

app = ConstantsModelCRUD(settings=settings, title="ConstantsModelCRUD")
