import sys
import copy

sys.path.append(".")

from src.common import model_crud_svc
from src.common import hierarchy
from src.common import model_copy
from src.common.hierarchy import CN_SCOPE_ONELEVEL, CN_SCOPE_SUBTREE
from src.services.methods.method_catalog import (
    catalog_id_from_message,
    error as catalog_error,
    ldap_first,
    parent_allows_initiator_cache,
    validate_method_message,
)
from src.services.methods.method_description import apply_method_description, parse_method_description
from src.services.methods.model_crud.method_package_loader import seed_method_packages
from src.services.methods.model_crud.methods_model_crud_settings import MethodsModelCRUDSettings


def _stored_object_classes(attrs: dict | None) -> list[str]:
    raw = (attrs or {}).get("objectClass") or (attrs or {}).get("objectclass") or []
    if isinstance(raw, (bytes, str)):
        raw = [raw]
    classes: list[str] = []
    for item in raw:
        if isinstance(item, bytes):
            item = item.decode()
        text = str(item or "").strip()
        if text and text not in classes:
            classes.append(text)
    return classes


class MethodsModelCRUD(model_crud_svc.ModelCRUDSvc):
    """Сервис работы с методами в иерархии.

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: MethodsModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    def _set_handlers(self):
        super()._set_handlers()
        self._handlers["prsMethod.api_crud.copy"] = self._copy_method
        self._handlers["prsMethod.api_crud.folder.create"] = self._folder_create
        self._handlers["prsMethod.api_crud.folder.read"] = self._folder_read
        self._handlers["prsMethod.api_crud.folder.update"] = self._folder_update
        self._handlers["prsMethod.api_crud.folder.delete"] = self._folder_delete
        self._handlers["prsMethod.api_crud.description.import"] = self._import_description
        self._add_app_handlers()

    async def _copy_method(self, mes: dict, routing_key: str | None = None) -> dict:
        source_id = mes.get("sourceId")
        parent_id = mes.get("parentId")
        if not source_id or not parent_id:
            return {"error": {"code": 422, "message": "Должны быть заданы sourceId и parentId."}}
        return await model_copy.copy_single_method(
            self._hierarchy,
            self._post_message,
            source_id=source_id,
            new_parent_id=parent_id,
            subtree_ids=frozenset(),
            id_map={},
        )

    async def _is_method_folder(self, node_id: str | None) -> bool:
        """Папка каталога — prsFolder под cn=methods.

        Старые папки prsModelNode ещё узнаются, пока сервис их не переписал.
        """
        root_id = self._config.hierarchy.get("node_id")
        if not node_id or not root_id or node_id == root_id:
            return False
        current = node_id
        for _ in range(64):
            try:
                node_class = await self._hierarchy.get_node_class(current)
            except Exception:
                return False
            if node_class not in ("prsFolder", "prsModelNode"):
                return False
            try:
                parent_id, _ = await self._hierarchy.get_parent(current)
            except Exception:
                return False
            if parent_id == root_id:
                return True
            if not parent_id or parent_id == current:
                return False
            current = parent_id
        return False

    async def _check_parent_class(self, parent_id: str) -> bool:
        if await super()._check_parent_class(parent_id):
            return True
        return await self._is_method_folder(parent_id)

    async def _placement(self, node_id: str | None) -> str:
        if not node_id:
            return "missing"
        if node_id == self._config.hierarchy.get("node_id"):
            return "catalog"
        try:
            node_class = await self._hierarchy.get_node_class(node_id)
        except Exception:
            return "unknown"
        if node_class in ("prsTag", "prsAlert"):
            return "instance"
        if node_class in ("prsFolder", "prsModelNode") and await self._is_method_folder(node_id):
            return "catalog"
        return "other"

    async def _load_catalog_method(self, method_id: str) -> dict | None:
        rows = await self._hierarchy.search(
            {"id": method_id, "attributes": ["prsMethodAddress", "objectClass"]}
        )
        if not rows:
            return None
        try:
            node_class = await self._hierarchy.get_node_class(method_id)
        except Exception:
            node_class = None
        if node_class != "prsMethod":
            return {"isCatalog": False, "address": None}
        parent_id, _ = await self._hierarchy.get_parent(method_id)
        address = ldap_first(rows[0][2], "prsMethodAddress", "")
        return {
            "isCatalog": await self._placement(parent_id) == "catalog",
            "address": str(address or "").strip(),
        }

    async def _prepare_method_write(self, mes: dict, *, creating: bool) -> dict | None:
        if mes is None:
            return catalog_error(422, "Пустое сообщение.")
        catalog_id, err = catalog_id_from_message(mes)
        if err:
            return err
        parent_id = mes.get("parentId")
        if creating and not parent_id:
            parent_id = self._config.hierarchy.get("node_id")
        old_parent = None
        if not creating:
            try:
                old_parent, _ = await self._hierarchy.get_parent(mes["id"])
            except Exception:
                old_parent = None
            if not parent_id:
                parent_id = old_parent
        placement = await self._placement(parent_id)
        if not creating and mes.get("parentId") and old_parent:
            old_placement = await self._placement(old_parent)
            if old_placement == "catalog" and placement == "instance" and not catalog_id:
                return catalog_error(422, "Нельзя переносить метод каталога в тег или тревогу.")
        catalog_address = None
        if catalog_id:
            catalog_node = await self._load_catalog_method(catalog_id)
            if not catalog_node:
                return catalog_error(422, "Метод каталога не найден.")
            if not catalog_node.get("isCatalog"):
                return catalog_error(422, "Указанный метод не входит в каталог.")
            catalog_address = catalog_node.get("address")
        return validate_method_message(
            mes,
            placement=placement,
            catalog_id=catalog_id,
            catalog_address=catalog_address,
            require_address=creating and placement == "catalog",
        )

    async def _create(self, mes: dict, routing_key: str | None = None) -> dict:
        if mes is None:
            mes = {}
        if mes.get("folder"):
            return await self._folder_create(mes, routing_key)
        err = await self._prepare_method_write(mes, creating=True)
        if err:
            return err
        return await super()._create(mes, routing_key)

    async def _node_is_catalog_folder(self, node_id: str | None) -> bool:
        if not node_id:
            return False
        try:
            node_class = await self._hierarchy.get_node_class(node_id)
        except Exception:
            return False
        if node_class == "prsFolder":
            return await self._user_folder_allowed(node_id) or await self._is_method_folder(node_id)
        return node_class == "prsModelNode" and await self._is_method_folder(node_id)

    async def _update(self, mes: dict, routing_key: str | None = None) -> dict:
        if await self._node_is_catalog_folder((mes or {}).get("id")):
            return await self._folder_update(mes, routing_key)
        err = await self._prepare_method_write(mes, creating=False)
        if err:
            return err
        return await super()._update(mes, routing_key)

    async def _method_is_referenced(self, method_id: str) -> bool:
        rows = await self._hierarchy.search(
            {
                "filter": {"objectClass": ["prsMethod"], "prsCatalogMethodId": [method_id]},
                "attributes": ["cn"],
            }
        )
        return bool(rows)

    async def _folder_parent_ok(self, parent_id: str | None) -> bool:
        return await self._placement(parent_id or self._config.hierarchy.get("node_id")) == "catalog"

    async def _find_method_by_address(self, address: str) -> str | None:
        root_id = self._config.hierarchy.get("node_id")
        rows = await self._hierarchy.search(
            {
                "base": root_id,
                "scope": hierarchy.CN_SCOPE_SUBTREE,
                "filter": {"objectClass": ["prsMethod"], "prsMethodAddress": [address]},
                "attributes": ["cn", "objectClass"],
            }
        )
        for row in rows or []:
            if "prsMethod" in _stored_object_classes(row[2]):
                return row[0]
        return None

    async def _ensure_description_folder(self, parent_id: str, folder: dict) -> tuple[str | None, str, str]:
        rows = await self._hierarchy.search(
            {
                "base": parent_id,
                "scope": hierarchy.CN_SCOPE_ONELEVEL,
                "filter": {"cn": [folder["cn"]], "objectClass": ["prsFolder"]},
                "attributes": ["cn", "objectClass"],
            }
        )
        for row in rows or []:
            classes = _stored_object_classes(row[2])
            if "prsFolder" in classes or ("prsModelNode" in classes and "prsMethod" not in classes):
                return row[0], "exists", ""
        attributes = {"cn": folder["cn"]}
        if folder.get("description"):
            attributes["description"] = folder["description"]
        created = await self._folder_create({"parentId": parent_id, "attributes": attributes})
        if created.get("error"):
            return None, "error", created["error"].get("message") or "Папка не создана."
        return created.get("id"), "created", ""

    async def _create_description_method(self, parent_id: str, method: dict) -> tuple[str | None, str, str]:
        payload = {
            "parentId": parent_id,
            "attributes": {
                "cn": method["cn"],
                **({"description": method["description"]} if method.get("description") else {}),
                "prsMethodAddress": method["prsMethodAddress"],
                "prsEntityTypeCode": 0,
            },
            "parameters": [
                {
                    "attributes": {
                        "cn": item["cn"],
                        "description": item.get("description") or "",
                        "prsIndex": item["prsIndex"],
                        "prsValueTypeCode": item["prsValueTypeCode"],
                    }
                }
                for item in method.get("parameters") or []
            ],
        }
        created = await self._create(payload)
        if not isinstance(created, dict) or created.get("error"):
            message = ""
            if isinstance(created, dict):
                message = (created.get("error") or {}).get("message") or ""
            return None, "error", message or "Метод не создан."
        return created.get("id"), "created", ""

    async def _import_description(self, mes: dict, routing_key: str | None = None) -> dict:
        text = (mes or {}).get("yaml") or (mes or {}).get("text") or ""
        parent_id = (mes or {}).get("parentId") or self._config.hierarchy.get("node_id")
        if parent_id in (None, "", "methods"):
            parent_id = self._config.hierarchy.get("node_id")
        if not await self._folder_parent_ok(parent_id):
            return catalog_error(422, "Описание загружается только в каталог методов.")
        try:
            tree = parse_method_description(text)
        except ValueError as ex:
            return catalog_error(422, str(ex))
        try:
            return await apply_method_description(
                tree,
                parent_id,
                ensure_folder=self._ensure_description_folder,
                create_method=self._create_description_method,
                find_by_address=self._find_method_by_address,
            )
        except Exception as ex:
            return catalog_error(422, f"Описание не загружено: {ex}")

    async def _folder_create(self, mes: dict, routing_key: str | None = None) -> dict:
        parent_id = (mes or {}).get("parentId") or self._config.hierarchy.get("node_id")
        if not await self._folder_parent_ok(parent_id):
            return catalog_error(422, "Папку методов можно создать только в каталоге методов.")
        attrs = dict((mes or {}).get("attributes") or {})
        attrs.pop("objectClass", None)
        attrs["objectClass"] = ["prsFolder"]
        if "prsActive" not in attrs:
            attrs["prsActive"] = True
        new_id = await self._hierarchy.add(parent_id, attrs)
        if not new_id:
            return catalog_error(422, "Папка методов не создана.")
        return {"id": new_id}

    async def _folder_read(self, mes: dict, routing_key: str | None = None) -> dict:
        payload = dict(mes or {})
        payload.pop("getParent", None)
        payload.pop("hierarchy", None)
        raw_filter = dict(payload.get("filter") or {})
        normalized_filter = {}
        for key, item in raw_filter.items():
            normalized_filter[key] = item if isinstance(item, list) else [item]
        normalized_filter["objectClass"] = ["prsFolder"]
        payload["filter"] = normalized_filter
        if not payload.get("base") and not payload.get("id"):
            payload["base"] = self._config.hierarchy.get("node_id")
            payload.setdefault("scope", CN_SCOPE_ONELEVEL)
        attributes = list(payload.get("attributes") or [])
        if "objectClass" not in attributes and "*" not in attributes:
            attributes.append("objectClass")
        payload["attributes"] = attributes
        try:
            items = await self._hierarchy.search(payload)
        except Exception as ex:
            return catalog_error(422, str(ex))
        data = []
        for item in items or []:
            classes = _stored_object_classes(item[2])
            if "prsFolder" not in classes:
                continue
            data.append({"id": item[0], "attributes": item[2]})
        return {"data": data}

    async def _folder_update(self, mes: dict, routing_key: str | None = None) -> dict:
        folder_id = (mes or {}).get("id")
        if not folder_id:
            return catalog_error(422, "Не указана папка методов.")
        try:
            node_class = await self._hierarchy.get_node_class(folder_id)
        except Exception:
            return catalog_error(422, f"Папка {folder_id} не найдена.")
        if not await self._node_is_catalog_folder(folder_id):
            return catalog_error(422, f"Узел {folder_id} не является папкой методов.")
        new_parent = mes.get("parentId")
        if new_parent and not await self._folder_parent_ok(new_parent):
            return catalog_error(422, "Папку методов можно перенести только внутри каталога.")
        attrs = dict(mes.get("attributes") or {})
        attrs.pop("objectClass", None)
        if attrs:
            await self._hierarchy.modify(folder_id, attrs)
        if new_parent:
            await self._hierarchy.move(folder_id, new_parent)
        return {}

    async def _descendant_method_ids(self, folder_id: str) -> list[str]:
        rows = await self._hierarchy.search(
            {
                "base": folder_id,
                "scope": CN_SCOPE_SUBTREE,
                "filter": {"objectClass": ["prsMethod"]},
                "attributes": ["cn"],
                "deref": False,
            }
        )
        return [row[0] for row in rows or [] if row[0] != folder_id]

    async def _folder_delete(self, mes: dict, routing_key: str | None = None) -> dict:
        raw_ids = (mes or {}).get("id")
        folder_ids = raw_ids if isinstance(raw_ids, list) else [raw_ids]
        for folder_id in folder_ids:
            if not folder_id:
                return catalog_error(422, "Не указана папка методов.")
            try:
                node_class = await self._hierarchy.get_node_class(folder_id)
            except Exception:
                return catalog_error(422, f"Папка {folder_id} не найдена.")
            if not await self._node_is_catalog_folder(folder_id):
                return catalog_error(422, f"Узел {folder_id} не является папкой методов.")
            for method_id in await self._descendant_method_ids(folder_id):
                if await self._method_is_referenced(method_id):
                    return {
                        "error": {
                            "code": 409,
                            "message": (
                                f"Папка содержит метод {method_id}, "
                                "на который ссылаются экземпляры (prsCatalogMethodId)."
                            ),
                        }
                    }
            for method_id in await self._descendant_method_ids(folder_id):
                await self._delete_method_cache(method_id)
            await self._hierarchy.delete(folder_id)
        return {}

    def _add_app_handlers(self):
        self._handlers["prsTag.model.deleted.*"] = self._delete_initiator
        self._handlers["prsSchedule.model.deleted.*"] = self._delete_initiator

    @staticmethod
    def _unwrap_redis_json_root(val):
        # RedisJSON GET path="$" wraps the document in a one-element array.
        # A real one-element list of method ids must stay a list.
        if isinstance(val, list) and len(val) == 1 and isinstance(val[0], (dict, list)):
            return val[0]
        return val

    @staticmethod
    def _is_missing_node_error(ex: BaseException) -> bool:
        return isinstance(ex, ValueError) and "не найден" in str(ex)

    async def _delete_initiator(self, mes: dict, routing_key: str):
        deleted_id = mes['id']
        obj_class = routing_key.split('.')[0]

        # отпишемся от событий инициатора
        await self._amqp_consume_queue.unbind(
            exchange=self._exchange,
            routing_key=f"{obj_class}.model.deleted.{deleted_id}"
        )

        # сообщим методам, что инициатор удалился, чтобы они могли отписаться от событий...
        async with self._cache.get_redis() as r:
            initiator_cache = self._unwrap_redis_json_root(
                await r.json().get(f"{deleted_id}.{self._config.svc_name}")
            )

            if initiator_cache is None:
                self._logger.error(f"{self._config.svc_name} :: Нет кэша для удалённого инициатора {deleted_id}.")
                return
            # удалим только кэш этого инициатора, не трогая ключи других инициаторов
            await r.json().delete(f"{deleted_id}.{self._config.svc_name}")

        if isinstance(initiator_cache, dict):
            method_ids = list(initiator_cache.keys())
        elif isinstance(initiator_cache, list):
            method_ids = list(initiator_cache)
        else:
            self._logger.error(
                f"{self._config.svc_name} :: Некорректный кэш удалённого инициатора {deleted_id}."
            )
            return

        for method_id in method_ids:
            try:
                payload = {
                    "base": method_id,
                    "filter": {"cn": deleted_id},
                    "attributes": ["cn"]
                }
                initiator = await self._hierarchy.search(payload=payload)
                if initiator:
                    await self._hierarchy.delete(initiator[0][0])
                    await self._post_message(
                        mes={"id": method_id},
                        routing_key=f"{self._config.hierarchy['class']}.model.updated.{method_id}"
                    )
                else:
                    self._logger.error(
                        f"{self._config.svc_name} :: Нет данных по инициатору '{deleted_id}' "
                        f"для метода '{method_id}'."
                    )
            except Exception as ex:
                self._logger.error(
                    f"{self._config.svc_name} :: Ошибка очистки инициатора '{deleted_id}' "
                    f"у метода '{method_id}': {ex}"
                )

    async def _make_method_cache(self, method_id: str):
        """Создаёт кэш метода для всех его инициаторов."""
        if not await parent_allows_initiator_cache(self._hierarchy, method_id):
            return
        initiators = await self._get_method_initiators(method_id)

        if not initiators:
            return

        async with self._cache.get_redis() as r:
            for initiator_id, initiator_data in initiators:
                obj_class = initiator_data["objectClass"][0]

                # если есть кэш для этого инициатора, добавляем метод
                # если нет, создаём
                initiator_cache = await r.json().get(f"{initiator_id}.{self._config.svc_name}")
                if initiator_cache is None:
                    await r.json().set(
                        name=f"{initiator_id}.{self._config.svc_name}",
                        path="$",
                        obj=[method_id]
                    )
                else:
                    # если path=$, то возвращается массив
                    # если элемент не найден, то первый элемент массива = -1
                    index = await r.json().arrindex(
                        f"{initiator_id}.{self._config.svc_name}", "$", method_id  # type: ignore[arg-type]
                    )

                    if index[0] == -1:
                        await r.json().arrappend(
                            f"{initiator_id}.{self._config.svc_name}", "$", method_id
                        )

                # подписываемся на событие удаления инициатора
                await self._amqp_consume_queue.bind(
                    exchange=self._exchange,
                    routing_key=f"{obj_class}.model.deleted.{initiator_id}"
                )

    async def _get_method_initiators(self, method_id: str) -> list[tuple[str, dict]]:
        """Получает список инициаторов для метода.

        Returns:
            list[tuple[str, dict]]: Список кортежей (initiator_id, initiator_data)
        """
        try:
            payload = {
                "base": method_id,
                "filter": {"cn": ["initiatedBy"]},
                "attributes": ["cn"]
            }
            initiatedBy_result = await self._hierarchy.search(payload=payload)
        except Exception as ex:
            if self._is_missing_node_error(ex):
                self._logger.warning(
                    f"{self._config.svc_name} :: Метод '{method_id}' уже удалён, "
                    "кэш инициаторов не читаем."
                )
                return []
            self._logger.error(
                f"{self._config.svc_name} :: Ошибка чтения инициаторов метода '{method_id}': {ex}"
            )
            return []

        if not initiatedBy_result:
            self._logger.warning(
                f"{self._config.svc_name} :: Не найден узел 'initiatedBy' для метода '{method_id}'."
            )
            return []

        initiatedBy_id = initiatedBy_result[0][0]
        payload = {
            "base": initiatedBy_id,
            "scope": hierarchy.CN_SCOPE_ONELEVEL,
            "filter": {"cn": ["*"]},
            "attributes": ["cn"]
        }
        initiators = await self._hierarchy.search(payload=payload)

        result = []
        for initiator in initiators:
            initiator_id = initiator[2]["cn"][0]
            payload = {"id": initiator_id, "attributes": ["objectClass"]}
            initiator_data = await self._hierarchy.search(payload=payload)
            if initiator_data:
                result.append((initiator_id, initiator_data[0][2]))

        return result

    async def _remove_method_from_initiator_cache(
        self, r, initiator_id: str, method_id: str, obj_class: str
    ) -> bool:
        """Удаляет метод из кэша инициатора и очищает кэш, если он пуст.

        Returns:
            bool: True если кэш был удалён, False иначе
        """
        initiator_cache = self._unwrap_redis_json_root(
            await r.json().get(f"{initiator_id}.{self._config.svc_name}")
        )

        if not initiator_cache or not isinstance(initiator_cache, list):
            return False

        try:
            index = initiator_cache.index(method_id)
        except ValueError:
            return False

        await r.json().arrpop(
            f"{initiator_id}.{self._config.svc_name}", "$", index
        )

        # Проверяем, остались ли ещё методы в кэше
        updated_cache = self._unwrap_redis_json_root(
            await r.json().get(f"{initiator_id}.{self._config.svc_name}")
        )
        if not updated_cache:
            # Кэш пуст, удаляем его и отписываемся от событий
            await self._amqp_consume_queue.unbind(
                exchange=self._exchange,
                routing_key=f"{obj_class}.model.deleted.{initiator_id}"
            )
            await r.json().delete(f"{initiator_id}.{self._config.svc_name}")
            return True

        return False

    async def _delete_method_cache(self, ids: str | list[str]):
        """Удаляет метод(ы) из кэша инициаторов.

        Args:
            ids: ID метода или список ID методов
        """
        method_ids = [ids] if isinstance(ids, str) else ids

        async with self._cache.get_redis() as r:
            for method_id in method_ids:
                try:
                    initiators = await self._get_method_initiators(method_id)
                except Exception as ex:
                    self._logger.warning(
                        f"{self._config.svc_name} :: Не удалось прочитать инициаторов "
                        f"метода '{method_id}' при очистке кэша: {ex}"
                    )
                    continue

                for initiator_id, initiator_data in initiators:
                    obj_class = initiator_data["objectClass"][0]
                    await self._remove_method_from_initiator_cache(
                        r, initiator_id, method_id, obj_class
                    )

    async def _further_create(self, mes: dict, new_id: str) -> None:
        system_node = await self._hierarchy.search(payload={
            "base": new_id,
            "scope": hierarchy.CN_SCOPE_ONELEVEL,
            "filter": {
                "cn": ["system"]
            },
            "attributes": ["cn"]
        })
        if not system_node:
            self._logger.error(f"{self._config.svc_name} :: В методе {new_id} отсутствует узел 'system'.")
            return

        system_node_id = system_node[0][0]

        # создадим список инициаторов расчёта
        initiatedBy_node_id = await self._hierarchy.add(
            system_node_id,
            {"cn": ["initiatedBy"]}
        )

        parent_node_id, _ = await self._hierarchy.get_parent(new_id)
        initiators = mes.get("initiatedBy")
        if (initiators is not None):
            if (parent_node_id in initiators):
                res = {
                    "id": None,
                    "error": {
                        "code": 400,
                        "message": "ParentId не может быть в списке 'initiatedBy'."
                    }
                }

                return res

            for initiator_id in mes["initiatedBy"]:
                await self._hierarchy.add(
                    initiatedBy_node_id,
                    {"cn": [initiator_id]}
                )

        # создадим узлы-параметры
        parameters_node_id = await self._hierarchy.add(
            system_node_id,
            {"cn": ["parameters"]}
        )
        if mes.get("parameters"):
            for parameter in mes["parameters"]:
                attrs = hierarchy.omit_empty_ldap_description(
                    parameter.setdefault("attributes", {})
                )
                attrs["objectClass"] = ["prsMethodParameter"]
                await self._hierarchy.add(
                    parameters_node_id,
                    attrs
                )

        payload = {
            "id": new_id,
            "attributes": ["prsActive"]
        }
        method_active = await self._hierarchy.search(payload=payload)
        if method_active[0][2]["prsActive"][0] == 'TRUE':
            await self._make_method_cache(new_id)

    async def _further_read(self, mes: dict, search_result: dict) -> dict:
        # добавим в результат параметры и initiatedBy
        new_result = {
            "data": []
        }

        for method_item in search_result["data"]:
            new_method_item = copy.deepcopy(method_item)
            object_class = ldap_first(new_method_item.get("attributes"), "objectClass", "")
            if object_class == "prsModelNode":
                new_result["data"].append(new_method_item)
                continue
            new_method_item["initiatedBy"] = []
            new_method_item["parameters"] = []

            # TODO: переработать, т.к. получать DN, потом составлять новый - плохая практика
            method_dn = await self._hierarchy.get_node_dn(new_method_item["id"])

            # ищем инициаторов
            initiated_by_node_dn = f"cn=initiatedBy,cn=system,{method_dn}"
            payload = {
                "base": initiated_by_node_dn,
                "scope": 1,
                "filter": {"cn": ["*"]},
                "attributes": ["cn"]
            }
            initiators = await self._hierarchy.search(payload)
            for initiator in initiators:
                new_method_item["initiatedBy"].append(initiator[2]["cn"][0])

            # ищем параметры
            parameters_node_dn = f"cn=parameters,cn=system,{method_dn}"
            payload = {
                "base": parameters_node_dn,
                "scope": 1,
                "filter": {"objectClass": ["prsMethodParameter"]},
                "attributes": [
                    "cn",
                    "description",
                    "prsActive",
                    "prsIndex",
                    "prsJsonConfigString",
                    "prsValueTypeCode",
                ]
            }
            parameters = await self._hierarchy.search(payload)
            for parameter in parameters:
                new_method_item["parameters"].append({
                    "attributes": parameter[2]
                })
            try:
                parent_id, _ = await self._hierarchy.get_parent(new_method_item["id"])
                if await self._placement(parent_id) == "catalog":
                    new_method_item["parameterCount"] = len(new_method_item["parameters"])
            except Exception:
                pass

            new_result["data"].append(new_method_item)
        return new_result

    async def _further_update(self, mes: dict) -> None:
        if "initiatedBy" in mes.keys():
            await self._delete_method_cache(mes['id'])
            # просто переделаем весь список инициаторов
            initiatedBy_node = await self._hierarchy.search(
                payload={"base": mes['id'], "filter": {"cn": ["initiatedBy"]}, "attributes": ["cn"]}
            )
            if not initiatedBy_node:
                self._logger.error(f"{self._config.svc_name} :: Не найден узел 'initiatedBy' для метода '{mes['id']}'.")
                return
            await self._hierarchy.delete(initiatedBy_node[0][0])

        if "parameters" in mes.keys():
            parameters_node = await self._hierarchy.search(payload={
                "base": mes["id"],
                "scope": hierarchy.CN_SCOPE_SUBTREE,
                "filter": {
                    "cn": ["parameters"]
                },
                "attributes": ["cn"]
            })
            if parameters_node:
                parameters_node_id = parameters_node[0][0]
                await self._hierarchy.delete(parameters_node_id)

        await self._further_create(mes, mes["id"])

    async def _get_methods(self):
        payload = {
            "filter": {"objectClass": ["prsMethod"], "prsActive": ["TRUE"]},
            "attributes": ["cn"]
        }
        methods = await self._hierarchy.search(payload=payload)
        for method in methods:
            await self._make_method_cache(method[0])

    async def _delete(self, mes: dict, routing_key: str = None) -> dict:
        raw_ids = mes.get("id")
        method_ids = raw_ids if isinstance(raw_ids, list) else [raw_ids]
        if method_ids and await self._node_is_catalog_folder(method_ids[0]):
            return await self._folder_delete(mes, routing_key)
        for method_id in method_ids:
            if method_id and await self._method_is_referenced(method_id):
                return {
                    "error": {
                        "code": 409,
                        "message": (
                            f"Метод {method_id} используется экземплярами (prsCatalogMethodId)."
                        ),
                    }
                }
        await self._delete_method_cache(mes['id'])
        return await super()._delete(mes)

    async def _rewrite_legacy_method_folders(self) -> None:
        """Старые папки каталога были prsModelNode. Приводим их к prsFolder."""
        root_id = self._config.hierarchy.get("node_id")
        if not root_id:
            return
        rows = await self._hierarchy.search({
            "base": root_id,
            "scope": hierarchy.CN_SCOPE_SUBTREE,
            "filter": {"objectClass": ["prsModelNode"]},
            "attributes": ["cn", "objectClass"],
            "deref": False,
        })
        for row in rows or []:
            if row[0] == root_id or not await self._is_method_folder(row[0]):
                continue
            if "prsFolder" in _stored_object_classes(row[2]):
                continue
            await self._hierarchy.modify(row[0], {"objectClass": ["prsFolder"]})

    async def on_startup(self) -> None:
        await super().on_startup()
        try:
            await self._rewrite_legacy_method_folders()
        except Exception as ex:
            self._logger.error(f"{self._config.svc_name} :: Старые папки методов не переписаны: {ex}")
        try:
            await seed_method_packages(
                self._hierarchy,
                self._config.hierarchy.get("node_id"),
                self._logger,
            )
        except Exception as ex:
            self._logger.error(f"{self._config.svc_name} :: Пакеты методов не загружены: {ex}")

        await self._amqp_consume_queue.unbind(self._exchange, "prsTag.model.deleted.*")
        await self._amqp_consume_queue.unbind(self._exchange, "prsSchedule.model.deleted.*")
        try:
            await self._get_methods()
        except Exception as ex:
            self._logger.error(f"{self._config.svc_name} :: {ex}")

settings = MethodsModelCRUDSettings()

app = MethodsModelCRUD(settings=settings, title="TagsModelCRUD")
