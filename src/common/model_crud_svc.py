"""
Модуль, содержащий базовый класс для управления экземплярами сущностей
в иерархии. По умолчанию, каждая сущность может иметь свой узел в иерархрии
для создания в нём своей иерархии, но это необязательно.
К примеру, наиболее используемая иерархия создаётся в узле ``objects``,
которым управляет сервис ``objects_model_crud_svc``.
"""
import sys
import copy
import asyncio
from uuid import UUID

sys.path.append(".")

from src.common.hierarchy import CN_SCOPE_ONELEVEL, CN_SCOPE_SUBTREE
from src.common.hierarchy_folders import node_class_from_object_classes
from src.common.svc import Svc
from src.common.model_crud_settings import ModelCRUDSettings

class ModelCRUDSvc(Svc):
    """
    Базовый класс для всех сервисов, работающих с экземплярами сущностей
    в иерархической модели.

    При запуске подписывается на сообщения
    обменника с именем, задаваемым в переменной окружения
    ``api_crud_exchange_name``,
    создавая очередь с именем из переменной ``api_crud_queue_name``.

    Сообщения, приходящие в эту очередь, создаются сервисом
    ``<сущность>_api_crud``.

    Общий формат сообщений, обрабатываемых сервисом:

    .. code:: json

       {
            "action": "<класс сущности>.model.<create | read | update | delete>"
            "data": {

            }
       }

    Форматы сообщений:

    **create**

    ``Message.reply_to`` = "имя ключа маршрутизации, с которым будет публиковаться ответ";

    ``Message.correlation_id`` = <идентификатор корреляции>;

    ``Message.body`` =

    .. code:: json

        {
            "action": "create",
            "data": {
                "parentId": "id of parent node",
                "attributes": {
                    "cn": "new node name",
                    "description": "some description"
                }
            }
        }

    В случае отсутствия ключа ``parentId`` в качестве родительского узла
    принимается базовый ключ сущности в иерархии. Например, для тегов -
    ``cn=tags,cn=prs``.

    В случае отсутствия в словаре атрибута ``cn``, в качестве значения
    этого атрибута принимается ``id`` (uuid) вновь созданного узла.

    Если в качестве значения атрибута ``cn`` передан массив значений, то
    в качестве имени узла принимается первое значение.

    Результат выполнения команды публикуется с ключом маршрутизации из
    параметра ``message.reply_to`` и идентификатором корреляции
    ``message.correlation_id`` и имеет формат ``message.body`` в случае
    успешного создания узла:

    .. code:: json

       {
            "id": "new_node_id"
       }

    ...и неудачи при создании:

    .. code:: json

        {
            "id": null,
            "error": {
                "code": 422,
                "message": "Ошибка создания узла."
            }
        }

    **read**:

    ``Message.reply_to`` = "имя ключа маршрутизации, с которым будет публиковаться ответ";

    ``Message.correlation_id`` = <идентификатор корреляции>;

    ``Message.body`` =

    .. code:: json

        {
            "action": "read",
            "data": {
                "id": ["first_id", "n_id"],
                "base": "base for search",
                "deref": true,
                "scope": 1,
                "filter": {
                    "prsActive": [true],
                    "prsEntityType": [1]
                },
                "attributes": ["cn", "description"]
            }
        }

    Результат выполнения команды =

    .. code:: json

        {
            "data": [
                {
                    "id": "node id",
                    "dn": "node dn",
                    "attributes": {
                    }
                }
            ]
        }

    **delete**:

    ``Message.reply_to`` = None

    ``Message.correlation_id`` = None

    ``Message.body`` =

    .. code:: json

        {
            "action": "delete",
            "data": {
                "id": ["first_id", "n_id"]
            }
        }

    Методы update и delete реализуют логику (разберем на примере update):
    1) Для узла ищутся все дети первого уровня.
    2) Определяется их класс
    3) Запускается сообщение <класс>.model.may_update.
       Это сообщение - вопрос всем "детям", можно ли удалить их родителя.
       Получаем на каждое сообщение ответ - можно или нет. Если хотя бы один ребёнок ответит "нет", то процедура
       прекращается.
    4) В случае положительных ответов от всех детей всем детям запускается сообщение <класс>.model.updating.
       Это предупреждение детям, что родитель сейчас будет удалён. Сообщение необходимо для того, чтобы дети
       могли себя корректно удалить.
    5) После получения ответов от всех детей производится обновление узла в иерархии и рассылается сообщение updated.

    """
    def __init__(self, settings: ModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

        self._config.hierarchy["node_dn"] = None
        self._config.hierarchy["node_id"] = None
        if self._config.hierarchy["parent_classes"]:
            classes = self._config.hierarchy["parent_classes"].split(",")
            self._config.hierarchy["parent_classes"] = [
                object_class.strip() for object_class in classes
            ]

    def _set_handlers(self):
        self._handlers = {
            f"{self._config.hierarchy['class']}.api_crud.create": self._create,
            f"{self._config.hierarchy['class']}.api_crud.read.*": self._read,
            f"{self._config.hierarchy['class']}.api_crud.update.*": self._update,
            f"{self._config.hierarchy['class']}.api_crud.delete.*": self._delete,
        }

    async def _update(self, mes: dict, routing_key: str | None = None) -> dict:
        """Метод обновления данных узла. Также метод может перемещать узел
        по иерархии.

        Args:
            data (dict): данные узла.
        """
        id = mes['id']

        if not await self._hierarchy.does_node_exist((id)):
            err_mes = f"Узел {id} не существует."
            self._logger.error(f"{self._config.svc_name} :: {err_mes}")
            res_response = {
                "error": {
                    "code": 422,
                    "message": err_mes
                }
            }
            return res_response

        node_class = await self._hierarchy.get_node_class(id)
        if node_class == "prsFolder":
            return await self._update_user_folder(mes)
        if node_class != self._config.hierarchy["class"]:
            err_mes = f"Узел {id} имеет необрабатываемый класс {node_class}."
            self._logger.error(f"{self._config.svc_name} :: {err_mes}")
            res_response = {
                "error": {
                    "code": 422,
                    "message": err_mes
                }
            }
            return res_response

        self._logger.debug(f"Обновление узла {id}...")

        new_parent = mes.get("parentId")
        if new_parent in ("objects", "tags", "connectors", "schedules", "dataStorages"):
            from src.common.hierarchy_folders import resolve_folder_parent_id

            resolved, resolve_error = await resolve_folder_parent_id(self._hierarchy, new_parent)
            if resolve_error:
                self._logger.error(f"{self._config.svc_name} :: {resolve_error}")
                return {"error": {"code": 422, "message": resolve_error}}
            new_parent = resolved
        if new_parent:
            if not await self._hierarchy.does_node_exist(new_parent):
                err_mes = f"Указанный в качестве нового родителя узел {new_parent} не существует."
                self._logger.error(f"{self._config.svc_name} :: {err_mes}")
                res_response = {
                    "error": {
                        "code": 422,
                        "message": err_mes
                    }
                }
                return res_response

            if not await self._check_parent_class(new_parent):
                err_mes = "Неправильный класс нового родительского узла."
                self._logger.error(f"{self._config.svc_name} :: {err_mes}")
                res_response = {
                    "error": {
                        "code": 422,
                        "message": err_mes
                    }
                }
                return res_response
            # проверка того, что новый родитель не является членом подиерархии узла
            res = await self._hierarchy.search({
                "base": id,
                "scope": CN_SCOPE_SUBTREE,
                "filter": {
                    "entryUUID": [new_parent]
                }
            })
            if res:
                err_mes = "Новый родительский узел содержится в подиерархии."
                self._logger.error(f"{self._config.svc_name} :: {err_mes}")
                res_response = {
                    "error": {
                        "code": 422,
                        "message": err_mes
                    }
                }
                return res_response

        # уведомим свой собственный сервис app об обновлении узла
        res = await self._post_message(
            mes=mes,
            reply=True,
            routing_key=f"{self._config.hierarchy['class']}.model.may_update.{id}"
        )
        if res is None:
            # это ветка, когда нет подписчика на событие may_update
            # то есть, по большому счёту, всем всё равно
            res = {"response": True}

        await self._post_message(
            mes=mes,
            reply=True,
            routing_key=f"{self._config.hierarchy['class']}.model.updating.{id}"
        )
        if mes.get("attributes"):
            try:
                await self._hierarchy.modify(id, mes["attributes"])
            except Exception as ex:
                err_mes = f"Ошибка обновления узла: {ex}."
                self._logger.error(f"{self._config.svc_name} :: {err_mes}")
                res_response = {
                    "error": {
                        "code": 422,
                        "message": err_mes
                    }
                }
                return res_response

        if new_parent:
            await self._hierarchy.move(id, new_parent)

        try:
            await self._further_update(mes)
        except Exception as ex:
            err_mes = f"Ошибка обновления узла: {ex}."
            self._logger.error(f"{self._config.svc_name} :: {err_mes}")
            return {
                "error": {
                    "code": 422,
                    "message": err_mes
                }
            }

        await self._post_message(
            mes={"id": id},
            reply=False,
            routing_key=f"{self._config.hierarchy['class']}.model.updated.{id}"
        )

        self._logger.info(f"{self._config.svc_name} :: Узел {id} обновлён.")

        return {}

    async def _further_update(self, mes: dict) -> None:
        """Метод переопределяется в сервисах-наследниках.
        В этом методе содержится специфическая работа при обновлении
        нового экземпляра сущности.
        Метод вызывается методом ``update`` после изменения узла в иерархии,
        но перед посылкой сообщения об изменении в очередь.

        Args:
            data (dict): id и атрибуты вновь создаваемого экземпляра сущности
        """

    async def _delete(self, mes: dict, routing_key: str | None = None) -> dict:
        """Метод удаляет экземпляр сущности из иерархии.
        Удаляем пока по одному узлу.

        Args:
            mes (dict): {"id": ["..."]}

        """
        ids = mes["id"]
        if not isinstance(ids, list):
            ids = [ids]

        for id in ids:

            if not (await self._hierarchy.does_node_exist((id))):
                err_mes = f"Узел {id} не существует."
                self._logger.error(f"{self._config.svc_name} :: {err_mes}")
                res_response = {
                    "error": {
                        "code": 422,
                        "message": err_mes
                    }
                }
                return res_response

            node_class = await self._hierarchy.get_node_class(id)
            if node_class == "prsFolder":
                folder_result = await self._delete_user_folder({"id": id})
                if isinstance(folder_result, dict) and folder_result.get("error"):
                    return folder_result
                continue
            if node_class != self._config.hierarchy["class"]:
                err_mes = f"Узел {id} имеет необрабатываемый класс {node_class}."
                self._logger.error(f"{self._config.svc_name} :: {err_mes}")
                res_response = {
                    "error": {
                        "code": 422,
                        "message": err_mes
                    }
                }
                return res_response

            self._logger.debug(f"Удаление узла {id}...")

            # логика уведомлений при удалении узла
            # уведомим свой собственный сервис app
            res = await self._post_message(
                mes=mes,
                reply=True,
                routing_key=f"{self._config.hierarchy['class']}.model.may_delete.{id}"
            )

            if res is None:
                # нет подписчика на сообщение
                res = {"response": True}

            if not res["response"]:
                err_mes = f"Нельзя удалить узел {id}."
                self._logger.error(f"{self._config.svc_name} :: {err_mes}")
                res_response = {
                    "error": {
                        "code": 422,
                        "message": err_mes
                    }
                }
                return res_response

            # получим список всех детей
            children = []
            items = await self._hierarchy.search(
                {
                    "base": id,
                    "scope": CN_SCOPE_SUBTREE,
                    "filter": {
                        "cn": ["*"]
                    },
                    "attributes": ["objectClass"],
                    "deref": False
                }
            )
            child_classes = self._config.hierarchy.get("child_classes", [])
            unnotified_classes = ["prsModelNode", "alias", "extensibleObject"] + child_classes
            for item in items:
                if item[0] == id:
                    # пропустим самого себя
                    continue

                objectClass = node_class_from_object_classes(item[2].get("objectClass"))
                if not (objectClass in unnotified_classes):
                    children.append({
                        "id": item[0],
                        "objectClass": objectClass
                    })
            if children:
                tasks = []
                for child in children:
                    future = asyncio.create_task(
                        self._post_message(
                            mes={"id": child["id"]},
                            reply=True,
                            routing_key=f"{child['objectClass']}.model.may_delete.{child['id']}"
                        ),
                        name=child['id']
                    )
                    tasks.append(future)

                # нельзя параллельно выполнять задачи - возникает ошибка при одновременном доступе к кэшу
                #done, _ = await asyncio.wait(
                #    tasks, return_when=asyncio.ALL_COMPLETED
                #)

                for future in tasks:
                    await future
                    res = future.result()
                    if res is None:
                        res = {"response": True}

                    if not res["response"]:
                        err_mes = f"Нельзя удалить узел {future.get_name()}: {res.get('message')}"
                        self._logger.error(f"{self._config.svc_name} :: {err_mes}")
                        res_response = {
                            "error": {
                                "code": 409,
                                "message": err_mes
                            }
                        }
                        return res_response

                for child in children:
                    await self._post_message(
                        {"id": child["id"]},
                        reply=True,
                        routing_key=f"{child['objectClass']}.model.deleting.{child['id']}"
                    )

                #done, _ = await asyncio.wait(
                #    tasks, return_when=asyncio.ALL_COMPLETED
                #)

            await self._further_delete(mes)

            parent_for_deleted_notify = None
            try:
                par = await self._hierarchy.get_parent(id)
                if par and par[0]:
                    parent_for_deleted_notify = par[0]
            except Exception:
                parent_for_deleted_notify = None

            await self._hierarchy.delete(id)

            deleted_mes = {"id": id}
            if parent_for_deleted_notify:
                deleted_mes["parentId"] = parent_for_deleted_notify
            await self._post_message(
                mes=deleted_mes, reply=False,
                routing_key=f"{self._config.hierarchy['class']}.model.deleted.{id}")

            for child in children:
                await self._post_message(
                    {"id": child["id"]},
                    reply=False,
                    routing_key=f"{child['objectClass']}.model.deleted.{child['id']}"
                )

            self._logger.info(f"{self._config.svc_name} :: Узел {id} удалён.")

            res_response = {}

        return res_response

    async def _further_delete(self, mes: dict) -> None:
        """Метод переопределяется в сервисах-наследниках.
        Используется для выполнения специфической работы при удалении
        экземпляра сущности.

        Вызывается методом ``delete`` после удаления узла в иерархии, но
        перед посылкой сообщения об удалении в очередь.

        Args:
            ids (List[str]): список ``id`` удаляемых узлов.
        """

    async def _read(self, mes: dict, routing_key: str | None = None) -> dict:
        """Правильность заполнения полей входного сообщения выполняется
        сервисом ``<сущность>_api_crud``.

        Args:
            mes(dict):

                .. code:: json

                    {
                        "action": "read",
                        "data": {
                            "id": ["first_id", "n_id"],
                            "base": "base for search",
                            "deref": true,
                            "scope": 1,
                            "filter": {
                                "prsActive": [true],
                                "prsEntityType": [1]
                            },
                            "attributes": ["cn", "description"]
                        }
                    }

        Returns:
            dict: словарь из найденных объектов

            .. code:: json

                {
                    "data": [
                        {
                            "id": "node id",
                            "attributes": {
                                "cn": ["name"],
                                "description": ["some description"]
                            }
                        }
                    ]
                }

        """

        async def hierarchy_search(payload: dict, *, _seen: set[str]) -> list[dict]:
            """Build a tree from LDAP subtree.

            Important: LDAP aliases (when deref is enabled) can create cycles,
            so we must protect against infinite recursion.
            """
            res: list[dict] = []
            items = await self._hierarchy.search(payload)
            for item in items:
                node_id = item[0]

                new_item: dict = {"id": node_id, "dn": item[1], "attributes": item[2]}
                if node_id in _seen:
                    new_item["children"] = []
                    res.append(new_item)
                    continue

                _seen.add(node_id)
                try:
                    new_payload = copy.deepcopy(payload)
                    new_payload["base"] = node_id
                    new_item["children"] = await hierarchy_search(new_payload, _seen=_seen)
                finally:
                    _seen.remove(node_id)

                res.append(new_item)
            return res

        res = {
            "data": []
        }

        mes_data = copy.deepcopy(mes)

        if mes_data.get("filter") is None:
            mes_data["filter"] = {}
        if mes_data["filter"].get("objectClass") is None:
            mes_data["filter"]["objectClass"] = [self._config.hierarchy["class"]]

        if mes_data["base"] == "prs":
            mes_data["base"] = await self._hierarchy.get_node_id("cn=prs")

        if mes_data["base"]:
            try:
                UUID(mes_data["base"])
            except Exception:
                base_name = mes_data["base"]
                if base_name in ("objects", "tags", "connectors", "schedules", "dataStorages", "methods"):
                    base_name = f"cn={base_name},cn=prs"
                node_id = await self._hierarchy.get_node_id(base_name)
                if node_id:
                    mes_data["base"] = node_id
                else:
                    if not self._config.hierarchy["node"]:
                        err_mes = "Должен быть указан родительский узел для поиска."
                        self._logger.error(f"{self._config.svc_name} :: {err_mes}")
                        res_response = {
                            "error": {
                                "code": 422,
                                "message": err_mes
                            }
                        }
                        return res_response

        if (not mes_data.get("base")) and (not mes_data.get("id")):
            if not self._config.hierarchy["node"]:
                err_mes = "Должен быть указан родительский узел для поиска."
                self._logger.error(f"{self._config.svc_name} :: {err_mes}")
                res_response = {
                    "error": {
                        "code": 422,
                        "message": err_mes
                    }
                }
                return res_response

            mes_data["base"] = self._config.hierarchy["node_id"]
        for key, item in mes_data["filter"].items():
            # если в запросе одно из полей было не списком, то делаем его списком
            if type(item) is not list:
                mes_data["filter"][key] = [mes_data["filter"][key]]

        if not mes_data["hierarchy"] or mes_data["scope"] < 2:
            try:
                items = await self._hierarchy.search(mes_data)
            except Exception as ex:
                return {"error": {"code": 422, "message": f"{ex}"}}

            for item in items:
                res["data"].append({
                    "id": item[0],
                    "dn": item[1],
                    "attributes": item[2]
                })
        else:
            # Папка — другой класс. Без неё обход hierarchy=true не заходит
            # внутрь prsFolder и теряет вложенные узлы. Без папок набор тот же.
            classes = list(mes_data["filter"].get("objectClass") or [])
            if "prsFolder" not in classes:
                mes_data["filter"]["objectClass"] = classes + ["prsFolder"]
            mes_data["scope"] = CN_SCOPE_ONELEVEL
            # For hierarchy mode we must not dereference aliases: it can jump outside the subtree
            # and create cycles (e.g. alias->target->...->alias).
            mes_data["deref"] = False
            items = await hierarchy_search(mes_data, _seen=set())
            for item in items:
                res["data"].append(item)

        if mes.get("getParent"):
            for item in res["data"]:
                parent_id, _ = await self._hierarchy.get_parent(item["id"])
                parent_class = await self._hierarchy.get_node_class(parent_id)
                item["parentId"] = (None, parent_id)[parent_class != "prsModelNode"]

        final_res = await self._further_read(mes, res)
        return final_res

    async def _further_read(self, mes: dict, search_result: dict) -> dict:
        """Метод переопределяется в классах-потомках, чтобы
        расширять результат поиска дополнительной информацией.
        """
        return search_result

    async def _create(self, mes: dict, routing_key: str | None = None) -> dict:
        """Метод создаёт новый экземпляр сущности в иерархии.

        Args:
            mes (dict): входные данные вида:

                .. code-block:: json

                    {
                        "parentId": "id родителя",
                        "attributes": {
                            "<ldap-attribute>": "<value>"
                        }
                    }

                ``parentId`` - id родительской сущности; в случае, если = None,
                то экзмепляр создаётся внутри базового для данной сущности
                узла; если ``parentId`` = None и нет базового узла, то
                генерируется ошибка.

                Среди атрибутов узла нет атрибута ``objectClass`` - метод
                добавляет его сам, вставляя значение из переменной окружения
                ``hierarchy_class``.

        Returns:
            dict: {"id": "new_id"}

        """

        if mes is None:
            mes = {}
        else:
            mes = dict(mes)
        if mes.pop("folder", False):
            return await self._create_user_folder(mes)
        parent_node = mes.get("parentId")
        parent_node = (self._config.hierarchy["node_id"], parent_node)[bool(parent_node)]
        if not parent_node:
            res = {
                "id": None,
                "error": {
                    "code": 422,
                    "message": "Не определён родительский узел."
                }
            }

            self._logger.error((
                f"{self._config.svc_name} :: Попытка создания узла {mes} "
                f"в неопределённом месте иерархии."
            ))

            return res

        if not await self._check_parent_class(parent_node):
            res = {
                "id": None,
                "error": {
                    "code": 422,
                    "message": "Неприемлемый класс родительского узла."
                }
            }

            self._logger.error((
                f"{self._config.svc_name} :: Попытка создания узла {mes} "
                f"в родительском узле неприемлемого класса."
            ))

            return res

        if not mes.get("attributes"):
            mes["attributes"] = {
                "objectClass": [self._config.hierarchy["class"]]
            }
        else:
            mes["attributes"]["objectClass"] = [self._config.hierarchy["class"]]

        items = await self._hierarchy.search(
                {
                    "base": parent_node,
                    "scope": CN_SCOPE_ONELEVEL,
                    "filter": {
                        "objectClass": [mes["attributes"]["objectClass"][0]],
                        "prsDefault": ["TRUE"]
                    },
                    "attributes": ["cn"]
                }
            )

        # логика создания узлов такова, что в списке узлов одного уровня
        # есть один узел с prsDefault = True
        # поэтому если по поиску выше не найдено узлов, то узлов в данном
        # уровне нет вообще
        if not items:
            mes["attributes"]["prsDefault"] = [True]
        else:
            # если есть уже дефолтный узел и делается попытка создать тоже
            # дефолтный, то существующий дефолтный должен стать обычным
            if mes["attributes"].get("prsDefault", False):
                await self._hierarchy.modify(
                    node=items[0][0],
                    attr_vals={
                        "prsDefault": ["FALSE"]
                    }
                )

        new_id = await self._hierarchy.add(parent_node, mes["attributes"])

        if not new_id:
            res = {
                "id": None,
                "error": {
                    "code": 422,
                    "message": "Ошибка создания узла."
                }
            }

            self._logger.error(f"{self._config.svc_name} :: Ошибка создания узла {mes}")

        else:
            res = {
                "id": new_id
            }
            self._logger.info(f"{self._config.svc_name} :: Создан новый узел {new_id}")

            # при необходимости создадим узел ``system``
            await self._hierarchy.add(new_id, {"cn": ["system"]})

            await self._further_create(mes, new_id)

            await self._post_message(
                mes={"id": new_id},
                reply=False,
                routing_key=f"{self._config.hierarchy['class']}.model.created"
            )

        return res

    async def _further_create(self, mes: dict, new_id: str) -> None:
        """Метод переопределяется в сервисах-наследниках.
        В этом методе содержится специфическая работа при создании
        нового экземпляра сущности.

        Метод вызывается методом ``create`` после создания узла в иерархии,
        но перед посылкой сообщения о создании в очередь.

        Args:
            data (dict): атрибуты вновь создаваемого экземпляра сущности;

            new_id (str): id уже созданного узла
        """

    def _folder_error(self, code: int, message: str) -> dict:
        return {"id": None, "error": {"code": code, "message": message}}

    async def _user_folder_allowed(self, node_id: str) -> bool:
        """Папка этой сущности допустима только в её ветке."""
        entity = self._config.hierarchy.get("class")
        if entity not in {"prsObject", "prsTag", "prsConnector", "prsSchedule", "prsDataStorage", "prsMethod"}:
            return False
        from src.common.hierarchy_folders import CONTEXT_CHILD_CLASSES, root_context

        context = await root_context(self._hierarchy, node_id)
        return entity in CONTEXT_CHILD_CLASSES.get(context or "", ())

    async def _create_user_folder(self, mes: dict) -> dict:
        """Создаёт ``prsFolder`` вместо экземпляра сущности.

        Пустой ``parentId`` — корень этого сервиса, как у обычного создания.
        """
        import ldap

        from src.common.hierarchy_folders import (
            folder_ldap_attributes,
            folder_name_error,
            folder_parent_allowed,
            resolve_folder_parent_id,
        )

        if self._config.hierarchy.get("class") not in {
            "prsObject", "prsTag", "prsConnector", "prsSchedule", "prsDataStorage", "prsMethod",
        }:
            return self._folder_error(422, "Эта сущность не создаёт папки.")
        parent_ref = (mes or {}).get("parentId") or self._config.hierarchy.get("node_id")
        parent_id, err = await resolve_folder_parent_id(self._hierarchy, parent_ref)
        if err:
            return self._folder_error(422, err)
        if not await folder_parent_allowed(self._hierarchy, parent_id):
            return self._folder_error(422, "Папку нельзя создать в этом узле.")
        if not await self._user_folder_allowed(parent_id):
            return self._folder_error(422, "Папку этой сущности нельзя создать в этой ветке.")
        attrs = folder_ldap_attributes((mes or {}).get("attributes"), creating=True)
        if not attrs.get("cn"):
            return self._folder_error(422, "Укажите имя папки (cn).")
        name_error = folder_name_error(attrs.get("cn"))
        if name_error:
            return self._folder_error(422, name_error)
        try:
            new_id = await self._hierarchy.add(parent_id, attrs)
        except ldap.ALREADY_EXISTS:
            return self._folder_error(422, "Узел с таким именем уже есть на этом уровне.")
        if not new_id:
            return self._folder_error(422, "Узел с таким именем уже есть на этом уровне.")
        self._logger.info(f"{self._config.svc_name} :: Создана папка {new_id}.")
        return {"id": new_id}

    async def _update_user_folder(self, mes: dict) -> dict:
        import ldap

        from src.common.hierarchy_folders import (
            folder_ldap_attributes,
            folder_move_error,
            folder_name_error,
            resolve_folder_parent_id,
        )

        folder_id = (mes or {}).get("id")
        if not folder_id:
            return self._folder_error(422, "Не указана папка.")
        if not await self._user_folder_allowed(folder_id):
            return self._folder_error(422, "Папка принадлежит другой ветке.")
        new_parent = mes.get("parentId")
        if new_parent:
            new_parent, err = await resolve_folder_parent_id(self._hierarchy, new_parent)
            if err:
                return self._folder_error(422, err)
            message = await folder_move_error(self._hierarchy, folder_id, new_parent)
            if message:
                return self._folder_error(422, message)
            if not await self._user_folder_allowed(new_parent):
                return self._folder_error(422, "Папку нельзя перенести в эту ветку.")
        attrs = folder_ldap_attributes(mes.get("attributes"), creating=False)
        name_error = folder_name_error(attrs.get("cn"))
        if name_error:
            return self._folder_error(422, name_error)
        try:
            if attrs:
                await self._hierarchy.modify(folder_id, attrs)
            if new_parent:
                current_parent, _ = await self._hierarchy.get_parent(folder_id)
                if current_parent != new_parent:
                    await self._hierarchy.move(folder_id, new_parent)
        except ldap.ALREADY_EXISTS:
            return self._folder_error(422, "Узел с таким именем уже есть на этом уровне.")
        return {}

    async def _user_folder_may_delete(self, folder_id: str) -> dict | None:
        rows = await self._hierarchy.search(
            {
                "base": folder_id,
                "scope": CN_SCOPE_SUBTREE,
                "filter": {"cn": ["*"]},
                "attributes": ["objectClass"],
                "deref": False,
            }
        )
        from src.common.hierarchy_folders import ENTITY_DELETE_ROUTING

        for row in rows or []:
            child_id = row[0]
            if child_id == folder_id:
                continue
            child_class = node_class_from_object_classes((row[2] or {}).get("objectClass"))
            if child_class in ("prsFolder", "prsModelNode", "alias", "extensibleObject", "top", ""):
                continue
            if child_class not in ENTITY_DELETE_ROUTING:
                return self._folder_error(422, f"В папке узел недопустимого класса {child_class}.")
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
                return self._folder_error(422, message)
        return None

    async def _delete_user_folder_node(self, folder_id: str) -> dict | None:
        from src.common.hierarchy_folders import ENTITY_DELETE_ROUTING

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
                return self._folder_error(422, f"Вложенный узел {child_id} не найден.")
            if child_class == "prsFolder":
                nested = await self._delete_user_folder_node(child_id)
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
                    return self._folder_error(422, f"Не удалось удалить вложенный узел {child_id}.")
                if isinstance(result, dict) and result.get("error"):
                    return result
                continue
            if child_class in ("prsModelNode", "alias", "extensibleObject"):
                await self._hierarchy.delete(child_id)
                continue
            return self._folder_error(422, f"В папке узел недопустимого класса {child_class}.")
        await self._hierarchy.delete(folder_id)
        return None

    async def _delete_user_folder(self, mes: dict) -> dict:
        raw_ids = (mes or {}).get("id")
        folder_ids = raw_ids if isinstance(raw_ids, list) else [raw_ids]
        for folder_id in folder_ids:
            if not folder_id:
                return self._folder_error(422, "Не указана папка.")
            if not await self._user_folder_allowed(folder_id):
                return self._folder_error(422, "Папка принадлежит другой ветке.")
            failed = await self._user_folder_may_delete(folder_id)
            if failed:
                return failed
            failed = await self._delete_user_folder_node(folder_id)
            if failed:
                return failed
            self._logger.info(f"{self._config.svc_name} :: Папка {folder_id} удалена.")
        return {}

    async def _check_parent_class(self, parent_id: str) -> bool:
        """Метод проверки того, что класс родительского узла
        соответствует необходимому. К примеру, тревоги могут создаваться только
        внутри тегов. То есть при создании новой тревоги мы должны убедиться,
        что класс родительского узла - ``prsTag``.

        Список всех возможных классов узлов-родителей указывается
        в конфигурации в переменной ``hierarchy_parent_classes``.

        Если у сущности нет собственного узла в иерархии и
        ``parent_id == None``, то вернётся ``False``.

        Args:
            parent_id (str): идентификатор родительского узла

        Returns:
            bool: True | False
        """

        if not parent_id:
            return False

        if self._config.hierarchy["node_id"] == parent_id:
            return True

        parent_classes = self._config.hierarchy.get("parent_classes") or []
        if not parent_classes:
            return False

        node_class = await self._hierarchy.get_node_class(parent_id)
        if node_class == "prsFolder":
            if "prsFolder" not in parent_classes:
                return False
            from src.common.hierarchy_folders import folder_accepts_child

            return await folder_accepts_child(
                self._hierarchy, parent_id, self._config.hierarchy["class"]
            )
        if node_class in parent_classes:
            return True

        return False

    async def _check_hierarchy_node(self) -> None:
        """Метод проверяет наличие базового узла сущности и, в случае его
        отсутствия, создаёт его.
        """
        if not self._config.hierarchy["node"]:
            return

        items = await self._hierarchy.search(payload={
            "scope": CN_SCOPE_ONELEVEL,
            "filter": {
                "cn": [f"{self._config.hierarchy['node']}"]
            },
            "attributes": ["entryUUID"]
        })
        if not items:
            base_node_id = await self._hierarchy.add(
                attribute_values={"cn": self._config.hierarchy["node"]}
            )
        else:
            base_node_id = items[0][0]

        self._config.hierarchy["node_dn"] = await self._hierarchy.get_node_dn(base_node_id)
        self._config.hierarchy["node_id"] = base_node_id

    async def on_startup(self) -> None:
        """Метод, выполняемый при старте приложения:
        происходит проверка базового узла сущности.
        :py:func:`model_crud_svc.ModelCRUDSvc._check_hierarchy_node`
        """
        await super().on_startup()
        await self._check_hierarchy_node()
