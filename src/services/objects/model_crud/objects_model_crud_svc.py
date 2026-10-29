import sys

import ldap

sys.path.append(".")

from src.common import model_crud_svc
from src.common import model_copy
from src.common.hierarchy import CN_SCOPE_ONELEVEL, CN_SCOPE_SUBTREE
from src.common.hierarchy_folders import (
    ENTITY_DELETE_ROUTING,
    ROOT_NAMES,
    folder_ldap_attributes,
    folder_move_error,
    folder_name_error,
    folder_parent_allowed,
    node_class_from_object_classes,
    node_ref_error,
    resolve_folder_parent_id,
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
        parent_id, err = await resolve_folder_parent_id(self._hierarchy, (mes or {}).get("parentId"))
        if err:
            return _error(422, err)
        if not await folder_parent_allowed(self._hierarchy, parent_id):
            return _error(422, "Папку нельзя создать в этом узле.")
        attrs = folder_ldap_attributes((mes or {}).get("attributes"), creating=True)
        if not attrs.get("cn"):
            return _error(422, "Укажите имя папки (cn).")
        name_error = folder_name_error(attrs.get("cn"))
        if name_error:
            return _error(422, name_error)
        try:
            new_id = await self._hierarchy.add(parent_id, attrs)
        except ldap.ALREADY_EXISTS:
            return _error(422, "Узел с таким именем уже есть на этом уровне.")
        if not new_id:
            return _error(422, "Узел с таким именем уже есть на этом уровне.")
        self._logger.info(f"{self._config.svc_name} :: Создана папка {new_id}.")
        return {"id": new_id}

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
        folder_id = (mes or {}).get("id")
        if not folder_id:
            return _error(422, "Не указана папка.")
        try:
            node_class = await self._hierarchy.get_node_class(folder_id)
        except Exception:
            return _error(422, f"Папка {folder_id} не найдена.")
        if node_class != "prsFolder":
            return _error(422, f"Узел {folder_id} не является папкой.")
        new_parent = mes.get("parentId")
        if new_parent:
            new_parent, err = await resolve_folder_parent_id(self._hierarchy, new_parent)
            if err:
                return _error(422, err)
            message = await folder_move_error(self._hierarchy, folder_id, new_parent)
            if message:
                return _error(422, message)
        attrs = folder_ldap_attributes(mes.get("attributes"), creating=False)
        name_error = folder_name_error(attrs.get("cn"))
        if name_error:
            return _error(422, name_error)
        try:
            if attrs:
                await self._hierarchy.modify(folder_id, attrs)
            if new_parent:
                current_parent, _ = await self._hierarchy.get_parent(folder_id)
                if current_parent != new_parent:
                    await self._hierarchy.move(folder_id, new_parent)
        except ldap.ALREADY_EXISTS:
            return _error(422, "Узел с таким именем уже есть на этом уровне.")
        return {}

    async def _folder_may_delete_tree(self, folder_id: str) -> dict | None:
        """Проверяет may_delete всего поддерева до первого удаления.

        Иначе veto на втором ребёнке оставляет уже удалённым первого.
        """
        rows = await self._hierarchy.search(
            {
                "base": folder_id,
                "scope": CN_SCOPE_SUBTREE,
                "filter": {"cn": ["*"]},
                "attributes": ["objectClass"],
                "deref": False,
            }
        )
        for row in rows or []:
            child_id = row[0]
            if child_id == folder_id:
                continue
            child_class = node_class_from_object_classes((row[2] or {}).get("objectClass"))
            if child_class in ("prsFolder", "prsModelNode", "alias", "extensibleObject", "top", ""):
                continue
            if child_class not in ENTITY_DELETE_ROUTING:
                return _error(422, f"В папке узел недопустимого класса {child_class}.")
            result = await self._post_message(
                mes={"id": child_id},
                reply=True,
                routing_key=f"{child_class}.model.may_delete.{child_id}",
            )
            if result is None:
                continue
            if isinstance(result, dict) and result.get("error"):
                return result
            if isinstance(result, dict) and not result.get("response", True):
                message = result.get("message") or f"Нельзя удалить вложенный узел {child_id}."
                return _error(422, message)
        return None

    async def _delete_folder_node(self, folder_id: str) -> dict | None:
        rows = await self._hierarchy.search(
            {
                "base": folder_id,
                "scope": CN_SCOPE_ONELEVEL,
                "filter": {"cn": ["*"]},
                "attributes": ["cn"],
                "deref": False,
            }
        )
        children = [row[0] for row in rows or [] if row[0] != folder_id]
        for child_id in children:
            try:
                child_class = await self._hierarchy.get_node_class(child_id)
            except Exception:
                return _error(422, f"Вложенный узел {child_id} не найден.")
            if child_class == "prsFolder":
                nested = await self._delete_folder_node(child_id)
                if nested:
                    return nested
                continue
            routing = ENTITY_DELETE_ROUTING.get(child_class)
            if routing:
                result = await self._post_message(
                    mes={"id": child_id},
                    reply=True,
                    routing_key=f"{routing}.{child_id}",
                )
                if result is None:
                    return _error(422, f"Не удалось удалить вложенный узел {child_id}.")
                if isinstance(result, dict) and result.get("error"):
                    return result
                continue
            if child_class in ("prsModelNode", "alias", "extensibleObject"):
                await self._hierarchy.delete(child_id)
                continue
            return _error(422, f"В папке узел недопустимого класса {child_class}.")
        await self._hierarchy.delete(folder_id)
        return None

    async def _folder_delete(self, mes: dict, routing_key: str | None = None) -> dict:
        raw_ids = (mes or {}).get("id")
        folder_ids = raw_ids if isinstance(raw_ids, list) else [raw_ids]
        for folder_id in folder_ids:
            if not folder_id:
                return _error(422, "Не указана папка.")
            try:
                node_class = await self._hierarchy.get_node_class(folder_id)
            except Exception:
                return _error(422, f"Папка {folder_id} не найдена.")
            if node_class != "prsFolder":
                return _error(422, f"Узел {folder_id} не является папкой.")
            failed = await self._folder_may_delete_tree(folder_id)
            if failed:
                return failed
            failed = await self._delete_folder_node(folder_id)
            if failed:
                return failed
            self._logger.info(f"{self._config.svc_name} :: Папка {folder_id} удалена.")
        return {}


settings = ObjectsModelCRUDSettings()

app = ObjectsModelCRUD(settings=settings, title="ObjectsModelCRUD")
