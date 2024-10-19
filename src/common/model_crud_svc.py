"""
Модуль, содержащий базовый класс для управления экземплярами сущностей
в иерархии. По умолчанию, каждая сущность может иметь свой узел в иерархрии
для создания в нём своей иерархии, но это необязательно.
К примеру, наиболее используемая иерархия создаётся в узле ``objects``\,
которым управляет сервис ``objects_model_crud_svc``\.
"""
import sys
import copy
import asyncio

sys.path.append(".")

from src.common.hierarchy import CN_SCOPE_ONELEVEL, CN_SCOPE_SUBTREE
from src.common.svc import Svc
from src.common.model_crud_settings import ModelCRUDSettings

class ModelCRUDSvc(Svc):
    """
    Базовый класс для всех сервисов, работающих с экземплярами сущностей
    в иерархической модели.

    При запуске подписывается на сообщения
    обменника с именем, задаваемым в переменной окружения
    ``api_crud_exchange_name``\,
    создавая очередь с именем из переменной ``api_crud_queue_name``\.

    Сообщения, приходящие в эту очередь, создаются сервисом
    ``<сущность>_api_crud``\.
    
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
    ``cn=tags,cn=prs``\.

    В случае отсутствия в словаре атрибута ``cn``\, в качестве значения
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
                "code": 406,
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
    
    async def _update(self, mes: dict, routing_key: str = None) -> dict:
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
                    "code": 406,
                    "message": err_mes
                }
            }
            return res_response

        node_class = await self._hierarchy.get_node_class(id)
        if node_class != self._config.hierarchy["class"]:
            err_mes = f"Узел {id} имеет необрабатываемый класс {node_class}."
            self._logger.error(f"{self._config.svc_name} :: {err_mes}")
            res_response = {
                "error": {
                    "code": 406,
                    "message": err_mes
                }
            }
            return res_response

        self._logger.debug(f"Обновление узла {id}...")

        new_parent = mes.get("parentId")
        if new_parent:
            if not self._hierarchy.does_node_exist(new_parent):
                err_mes = f"Указанный в качестве нового родителя узел {new_parent} не существует."
                self._logger.error(f"{self._config.svc_name} :: {err_mes}")
                res_response = {
                    "error": {
                        "code": 406,
                        "message": err_mes
                    }
                }
                return res_response

            if not self._check_parent_class(new_parent):
                err_mes = "Неправильный класс нового родительского узла."
                self._logger.error(f"{self._config.svc_name} :: {err_mes}")
                res_response = {
                    "error": {
                        "code": 406,
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
                        "code": 406,
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
            
        res = await self._post_message(
            mes=mes,
            reply=True,
            routing_key=f"{self._config.hierarchy['class']}.model.updating.{id}"
        )
        
        if mes.get("attributes"):
            await self._hierarchy.modify(id, mes["attributes"])
        if new_parent:
            await self._hierarchy.move(id, new_parent)

        await self._further_update(mes)

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

    async def _delete(self, mes: dict, routing_key: str = None) -> None:
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
                        "code": 406,
                        "message": err_mes
                    }
                }
                return res_response

            node_class = await self._hierarchy.get_node_class(id)
            if node_class != self._config.hierarchy["class"]:
                err_mes = f"Узел {id} имеет необрабатываемый класс {node_class}."
                self._logger.error(f"{self._config.svc_name} :: {err_mes}")
                res_response = {
                    "error": {
                        "code": 406,
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
                        "code": 409,
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
                    "attributes": ["objectClass"]
                }
            )
            for item in items:
                if item[0] == id:
                    # пропустим самого себя
                    continue

                objectClass = item[2]["objectClass"][0]
                if objectClass != "prsModelNode":
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

                done, _ = await asyncio.wait(
                    tasks, return_when=asyncio.ALL_COMPLETED
                )

                for future in done:
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

                tasks = []
                for child in children:
                    future = asyncio.create_task(
                        self._post_message(
                            {"id": child["id"]},
                            reply=True,
                            routing_key=f"{child['objectClass']}.model.deleting.{child['id']}"
                        ),
                        name=child['id']
                    )
                    tasks.append(future)

                done, _ = await asyncio.wait(
                    tasks, return_when=asyncio.ALL_COMPLETED
                )

            await self._further_delete(mes)

            await self._hierarchy.delete(id)

            await self._post_message(
                mes={"id": id}, reply=False, 
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

    async def _read(self, mes: dict, routing_key: str = None) -> dict:
        """Правильность заполнения полей входного сообщения выполняется
        сервисом ``<сущность>_api_crud``\.

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

        async def hierarchy_search(payload):
            res = []
            items = await self._hierarchy.search(payload)
            for item in items:
                new_payload = copy.deepcopy(payload)
                new_payload["base"] = item[0]

                new_item = {}
                new_item["id"] = item[0]
                new_item["attributes"] = item[2]
                new_item["children"] = await hierarchy_search(new_payload)
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

        if (not mes_data.get("base")) and (not mes_data.get("id")):
            if not self._config.hierarchy["node"]:
                err_mes = "Должен быть указан родительский узел для поиска."
                self._logger.error(f"{self._config.svc_name} :: {err_mes}")
                res_response = {
                    "error": {
                        "code": 406,
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
            items = await self._hierarchy.search(mes_data)
            for item in items:
                res["data"].append({
                    "id": item[0],
                    "attributes": item[2]
                })
        else:
            mes_data["scope"] = CN_SCOPE_ONELEVEL
            items = await hierarchy_search(mes_data)
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

    async def _create(self, mes: dict, routing_key: str = None) -> dict:
        """Метод создаёт новый экземпляр сущности в иерархии.

        Args:
            mes (dict): входные данные вида:

                .. code-block:: json

                    {
                        "action": "...",
                        "data": {
                            "parentId": "id родителя",
                            "attributes": {
                                "<ldap-attribute>": "<value>"
                            }
                        }
                    }

                ``parentId`` - id родительской сущности; в случае, если = None,
                то экзмепляр создаётся внутри базового для данной сущности
                узла; если ``parentId`` = None и нет базового узла, то
                генерируется ошибка.

                Среди атрибутов узла нет атрибута ``objectClass`` - метод
                добавляет его сам, вставляя значение из переменной окружения
                ``hierarchy_class``\.

        Returns:
            dict: {"id": "new_id"}

        """

        if mes is None:
            mes = {}
        parent_node = mes.get("parentId")
        parent_node = (self._config.hierarchy["node_id"], parent_node)[bool(parent_node)]
        if not parent_node:
            res = {
                "id": None,
                "error": {
                    "code": 406,
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
                    "code": 406,
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
            mes["attributes"]["prsDefault"] = True
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
                    "code": 406,
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

    async def _check_parent_class(self, parent_id: str) -> bool:
        """Метод проверки того, что класс родительского узла
        соответствует необходимому. К примеру, тревоги могут создаваться только
        внутри тегов. То есть при создании новой тревоги мы должны убедиться,
        что класс родительского узла - ``prsTag``\.

        Список всех возможных классов узлов-родителей указывается
        в конфигурации в переменной ``hierarchy_parent_classes``\.

        Если у сущности нет собственного узла в иерархии и
        ``parent_id == None``\, то вернётся ``False``\.

        Args:
            parent_id (str): идентификатор родительского узла

        Returns:
            bool: True | False
        """

        if not parent_id:
            return False

        if self._config.hierarchy["node_id"] == parent_id:
            return True

        if self._config.hierarchy["parent_classes"]:
            node_class = await self._hierarchy.get_node_class(parent_id)
            if (node_class in
                self._config.hierarchy["parent_classes"]):
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
