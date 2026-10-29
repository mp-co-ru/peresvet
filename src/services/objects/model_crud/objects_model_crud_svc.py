import sys

sys.path.append(".")

from src.common import model_crud_svc
from src.common import model_copy
from src.common.hierarchy import CN_SCOPE_ONELEVEL
from src.common.hierarchy_folders import (
    ROOT_NAMES,
    node_class_from_object_classes,
    node_ref_error,
)
from src.services.objects.model_crud.objects_model_crud_settings import ObjectsModelCRUDSettings


def _error(code: int, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


class ObjectsModelCRUD(model_crud_svc.ModelCRUDSvc):
    """Сервис работы с объектами в иерархии.

    Подписывается на очередь ``objects_api_crud`` обменника ``objects_api_crud``,
    в которую публикует сообщения сервис ``objects_api_crud`` (все имена
    указываются в переменных окружения).

    Пользовательские папки (``prsFolder``) обрабатываются здесь же:
    отдельного процесса для них нет.

    Формат ожидаемых сообщений

    """
    def __init__(self, settings: ObjectsModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    def _set_handlers(self):
        super()._set_handlers()
        self._handlers["prsObject.api_crud.copy"] = self._copy_subtree
        self._handlers["prsFolder.api_crud.create"] = self._folder_create
        self._handlers["prsFolder.api_crud.read"] = self._folder_read
        self._handlers["prsFolder.api_crud.update"] = self._folder_update
        self._handlers["prsFolder.api_crud.delete"] = self._folder_delete

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

    async def _folder_create(self, mes: dict, routing_key: str | None = None) -> dict:
        return await self._create_user_folder(mes)

    async def _folder_read(self, mes: dict, routing_key: str | None = None) -> dict:
        payload = dict(mes or {})
        get_parent = bool(payload.pop("getParent", None))
        payload.pop("hierarchy", None)
        payload.pop("deref", None)
        allowed_filter = {"cn", "description", "prsActive", "prsIndex"}
        raw_filter = payload.get("filter") or {}
        if not isinstance(raw_filter, dict):
            return _error(422, "Некорректный filter.")
        normalized = {}
        for key, item in raw_filter.items():
            if key not in allowed_filter:
                return _error(422, "Недопустимое поле фильтра.")
            values = item if isinstance(item, list) else [item]
            for value in values:
                if node_ref_error(str(value)) and str(value) != "*":
                    return _error(422, "Недопустимое значение фильтра.")
            normalized[key] = values
        normalized["objectClass"] = ["prsFolder"]
        payload["filter"] = normalized
        base = payload.get("base")
        if isinstance(base, str) and base in ("methods",):
            return _error(422, "Каталог методов не содержит пользовательских папок.")
        if isinstance(base, str) and base in ROOT_NAMES:
            node_id = await self._hierarchy.get_node_id(f"cn={base},cn=prs")
            if not node_id:
                return _error(422, f"Корень {base} не найден.")
            payload["base"] = node_id
        elif base == "prs":
            payload["base"] = await self._hierarchy.get_node_id("cn=prs")
        if not payload.get("base") and not payload.get("id"):
            payload["base"] = await self._hierarchy.get_node_id("cn=prs")
        payload.setdefault("scope", CN_SCOPE_ONELEVEL)
        attributes = list(payload.get("attributes") or ["cn"])
        if "objectClass" not in attributes and "*" not in attributes:
            attributes.append("objectClass")
        payload["attributes"] = attributes
        try:
            items = await self._hierarchy.search(payload)
        except Exception:
            self._logger.error(f"{self._config.svc_name} :: Не удалось прочитать папки.")
            return _error(422, "Не удалось прочитать папки.")
        data = []
        for item in items or []:
            classes = (item[2] or {}).get("objectClass") or []
            if node_class_from_object_classes(classes) != "prsFolder":
                continue
            row = {"id": item[0], "attributes": item[2]}
            if len(item) > 1 and item[1]:
                row["dn"] = item[1]
            data.append(row)
        if get_parent:
            for item in data:
                try:
                    parent_id, _ = await self._hierarchy.get_parent(item["id"])
                    parent_class = await self._hierarchy.get_node_class(parent_id)
                except Exception:
                    parent_id, parent_class = None, "prsModelNode"
                item["parentId"] = (None, parent_id)[parent_class != "prsModelNode"]
        return {"data": data}

    async def _folder_update(self, mes: dict, routing_key: str | None = None) -> dict:
        return await self._update_user_folder(mes)

    async def _folder_delete(self, mes: dict, routing_key: str | None = None) -> dict:
        return await self._delete_user_folder(mes)

settings = ObjectsModelCRUDSettings()

app = ObjectsModelCRUD(settings=settings, title="ObjectsModelCRUD")
