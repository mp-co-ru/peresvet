import sys
import copy

sys.path.append(".")

from src.common import model_crud_svc
from src.services.objects.model_crud.objects_model_crud_settings import ObjectsModelCRUDSettings

class ObjectsModelCRUD(model_crud_svc.ModelCRUDSvc):
    """Сервис работы с объектами в иерархии.

    Подписывается на очередь ``objects_api_crud`` обменника ``objects_api_crud``\,
    в которую публикует сообщения сервис ``objects_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """
    def __init__(self, settings: ObjectsModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    def __init__(self, settings: ObjectsModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

settings = ObjectsModelCRUDSettings()

app = ObjectsModelCRUD(settings=settings, title="ObjectsModelCRUD")
