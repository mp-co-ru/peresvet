import sys

sys.path.append(".")

from src.common import model_crud_svc
from src.common import model_copy
from src.services.alerts.model_crud.alerts_model_crud_settings import AlertsModelCRUDSettings

class AlertsModelCRUD(model_crud_svc.ModelCRUDSvc):
    """Сервис работы с тегами в иерархии.

    Подписывается на очередь ``tags_api_crud`` обменника ``tags_api_crud``,
    в которую публикует сообщения сервис ``tags_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: AlertsModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    def _set_handlers(self):
        super()._set_handlers()
        self._handlers["prsAlert.api_crud.copy"] = self._copy_subtree

    async def _copy_subtree(self, mes: dict, routing_key: str | None = None) -> dict:
        source_id = mes.get("sourceId")
        parent_id = mes.get("parentId")
        new_cn = None
        attrs = mes.get("attributes")
        if isinstance(attrs, dict):
            new_cn = attrs.get("cn")
        if not source_id or not parent_id:
            return {"error": {"code": 422, "message": "Должны быть заданы sourceId и parentId."}}
        return await model_copy.copy_subtree_rooted_at(
            self._hierarchy,
            self._post_message,
            root_source_id=source_id,
            expected_root_class="prsAlert",
            new_parent_id=parent_id,
            new_root_cn=new_cn,
        )

settings = AlertsModelCRUDSettings()

app = AlertsModelCRUD(settings=settings, title="AlertsModelCRUD")
