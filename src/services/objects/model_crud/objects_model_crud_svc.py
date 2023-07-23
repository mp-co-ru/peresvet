import sys
import copy

sys.path.append(".")

from objects_model_crud_settings import ObjectsModelCRUDSettings
from src.common import model_crud_svc

class ObjectsModelCRUD(model_crud_svc.ModelCRUDSvc):
    """Сервис работы с объектами в иерархии.

    Подписывается на очередь ``objects_api_crud`` обменника ``objects_api_crud``,
    в которую публикует сообщения сервис ``objects_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """
    _outgoing_commands = {
        "created": "objects.created",
        "mayUpdate": "objects.mayUpdate",
        "updating": "objects.updating",
        "updated": "objects.updated",
        "mayDelete": "objects.mayDelete",
        "deleting": "objects.deleting",
        "deleted": "objects.deleted"
    }

    def __init__(self, settings: ObjectsModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    def _set_incoming_commands(self) -> dict:
        return {
            "objects.create": self._create,
            "objects.read": self._read,
            "objects.update": self._update,
            "objects.delete": self._delete,
        }

    def __init__(self, settings: ObjectsModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

settings = ObjectsModelCRUDSettings()

app = ObjectsModelCRUD(settings=settings, title="ObjectsModelCRUD")
