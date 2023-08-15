import sys
import copy

sys.path.append(".")

from src.services.alerts.model_crud.alerts_model_crud_settings import AlertsModelCRUDSettings
from src.common import model_crud_svc
from src.common import hierarchy

class AlertsModelCRUD(model_crud_svc.ModelCRUDSvc):
    """Сервис работы с тегами в иерархии.

    Подписывается на очередь ``tags_api_crud`` обменника ``tags_api_crud``,
    в которую публикует сообщения сервис ``tags_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    _outgoing_commands = {
        "created": "alerts.created",
        "mayUpdate": "alerts.mayUpdate",
        "updating": "alerts.updating",
        "updated": "alerts.updated",
        "mayDelete": "alerts.mayDelete",
        "deleting": "alerts.deleting",
        "deleted": "alerts.deleted"
    }

    def __init__(self, settings: AlertsModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    def _set_incoming_commands(self) -> dict:
        return {
            "alerts.create": self._create,
            "alerts.read": self._read,
            "alerts.update": self._update,
            "alerts.delete": self._delete,
        }

settings = AlertsModelCRUDSettings()

app = AlertsModelCRUD(settings=settings, title="AlertsModelCRUD")
