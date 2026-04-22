import sys

sys.path.append(".")

from src.common import model_crud_svc
from src.common import model_copy
from src.services.objects.model_crud.objects_model_crud_settings import ObjectsModelCRUDSettings

class ObjectsModelCRUD(model_crud_svc.ModelCRUDSvc):
    """Сервис работы с объектами в иерархии.

    Подписывается на очередь ``objects_api_crud`` обменника ``objects_api_crud``,
    в которую публикует сообщения сервис ``objects_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """
    def __init__(self, settings: ObjectsModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    def _set_handlers(self):
        super()._set_handlers()
        self._handlers["prsObject.api_crud.copy"] = self._copy_subtree

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
            expected_root_class="prsObject",
            new_parent_id=parent_id,
            new_root_cn=new_cn,
        )

settings = ObjectsModelCRUDSettings()

app = ObjectsModelCRUD(settings=settings, title="ObjectsModelCRUD")
