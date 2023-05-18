"""
Модуль, содержащий базовый класс для управления экземплярами сущностей
в иерархии. По умолчанию, каждая сущность может иметь свой узел в иерархрии
для создания в нём своей иерархии, но это необязательно.
К примеру, наиболее используемая иерархия создаётся в узле ``objects``,
которым управляет сервис ``objects_model_crud_svc``.
"""

from typing import Annotated, Any, List
import asyncio
import json

import aio_pika
import aio_pika.abc

from hierarchy import CN_SCOPE_ONELEVEL, CN_SCOPE_SUBTREE
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
    Часть сообщений эмулируют RPC, у них параметр ``reply_to`` содержит имя
    очереди, в которую нужно отдать результат.
    Это сообщения: создание, поиск. Другие же сообщения (update, delete)
    не предполагают ответа.

    Общий формат сообщений, обрабатываемых сервисом:

    .. code:: json

       {
            "action": "create | read | update | delete",
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

    Args:
        settings (ModelCRUDSettings): конфигурация сервиса.

    """

    def __init__(self, settings: ModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

        self._conf.hierarchy["node_dn"]: str = None
        self._conf.hierarchy["node_id"]: str = None
        if settings._conf.hierarchy["parent_classes"]:
            classes = settings._conf.hierarchy["parent_classes"].split(",")
            self._conf.hierarchy["parent_classes"] = [
                object_class.strip() for object_class in classes
            ]

        self._api_crud_exchange: aio_pika.abc.AbstractRobustExchange = None
        self._api_crud_queue: aio_pika.abc.AbstractRobustQueue = None

    async def _amqp_connect(self) -> None:
        """Связь с amqp-сервером.
        В дополнение к обменнику, создаваемому классом-предком
        :class:`svc.Svc`, в этом методе
        создаётся обменник и очередь для получения сообщений от сервиса
        ``<сущность>_api_crud_svc``.

        """
        await super()._amqp_connect()

        self._api_crud_exchange = await self._amqp_channel.declare_exchange(
            self._config.api_crud_exchange["name"],
            type=self._config.api_crud_exchange["type"],
            durable=True
        )
        self._api_crud_queue = await self._amqp_channel.declare_queue(
            self._config.api_crud_exchange["queue_name"],
            durable=True
        )
        await self._api_crud_queue.bind(
            exchange=self._api_crud_exchange,
            routing_key=self._config.api_crud_exchange["routing_key"]
        )
        await self._api_crud_queue.consume(self._process_message)

    async def _process_message(self,
            message: aio_pika.abc.AbstractIncomingMessage
    ) -> None:
        """Метод обработки сообщений от сервиса ``<сущность>_api_crud_svc``.

        Сообщения должны приходить в формате:

        .. code:: json

            {
                "action": "create/read/update/delete",
                "data: {}
            }

        где

        * **action** - команда ("create", "read", "update", "delete"), при
          этом строчные или прописные буквы - не важно;
        * **data** - параметры команды.

        После выполнения соответствующей команды входное сообщение квитируется
        (``messsage.ack()``).

        В случае, если в сообщении установлен параметр ``reply_to``,
        то квитирование происходит после публикации ответного сообщения в
        очередь, указанную в ``reply_to``.

        """
        async with message.process(ignore_processed=True):
            mes = message.body.decode()
            try:
                mes = json.loads(mes)
            except json.decoder.JSONDecodeError:
                self._logger.error(f"Сообщение {mes} не в формате json.")
                await message.ack()
                return

            action = mes.get("action")
            if not action:
                self._logger.error(f"В сообщении {mes} не указано действие.")
                await message.ack()
                return

            action = action.lower()
            if action == "create":
                res = await self._create(mes)
            elif action == "update":
                res = await self._update(mes)
            elif action == "read":
                res = await self._read(mes)
            elif action == "delete":
                res = await self._delete(mes)
            else:
                self._logger.error(f"Неизвестное действие: {action}.")
                await message.ack()
                return

            if not message.reply_to:
                await message.ack()
                return

            await self._api_crud_exchange.publish(
                aio_pika.Message(
                    body=res,
                    correlation_id=message.correlation_id,
                ),
                routing_key=message.reply_to,
            )
            await message.ack()

    async def _update(self, data: dict) -> None:
        """Метод обновления данных узла. Также метод может перемещать узел
        по иерархии.

        Args:
            data (dict): данные узла.
        """

        new_parent = data.get("parentId")
        if new_parent:
            if self._check_parent_class(new_parent):
                self._hierarchy.move(data['id'], new_parent)
            else:
                self._logger.error("Неправильный класс нового родительского узла.")
                return

        self._hierarchy.modify(data["id"], data["attributes"])
        self._updating(data)
        await self._pub_exchange.publish(
            aio_pika.Message(
                body=f'{{"action": "updated", "id": {data["id"]}}}'.encode(),
                content_type='application/json',
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=self._config.pub_exchange["routing_key"]
        )
        self._logger.info(f'Узел {data["id"]} обновлён.')

    async def _updating(self, data: dict) -> None:
        """Метод переопределяется в сервисах-наследниках.
        В этом методе содержится специфическая работа при обновлении
        нового экземпляра сущности.
        Метод вызывается методом ``update`` после изменения узла в иерархии,
        но перед посылкой сообщения об изменении в очередь.

        Args:
            data (dict): id и атрибуты вновь создаваемого экземпляра сущности
        """

    async def _delete(self, ids: List[str]) -> None:
        """Метод удаляет экземпляр сущности из иерархии.

        Args:
            ids (List[str]): список идентификаторов узлов
        """
        for node in ids:
            self._hierarchy.delete(node)

        await self._pub_exchange.publish(
            aio_pika.Message(
                body=f'{{"action": "deleted", "id": {ids}}}'.encode(),
                content_type='application/json',
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=self._config.pub_exchange["routing_key"]
        )
        self._logger.info(f'Узлы {ids} удалены.')

    async def _deleting(self, ids: List[str]) -> None:
        """Метод переопределяется в сервисах-наследниках.
        Используется для выполнения специфической работы при удалении
        экземпляра сущности.

        Вызывается методом ``delete`` после удаления узла в иерархии, но
        перед посылкой сообщения об удалении в очередь.

        Args:
            ids (List[str]): список ``id`` удаляемых узлов.
        """

    async def _read(self, mes: dict) -> dict:
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

        res = {
            "data": []
        }
        for id_, _, attributes in await self._hierarchy.search(mes["data"]):
            res["data"].append({
                "id": id_,
                "attributes": attributes
            })

        return await self._reading(mes, res)

    async def _reading(self, data: dict, search_result: dict) -> dict:
        """Метод переопределяется в классах-потомках, чтобы
        расширять результат поиска дополнительной информацией.
        """

    async def _create(self, data: dict) -> dict:
        """Метод создаёт новый экземпляр сущности в иерархии.

        Args:
            data (dict): входные данные вида:

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

        parent_node = data.get("parentId")
        parent_node = parent_node if parent_node else self._config.hierarchy["node_id"]
        if not parent_node:
            res = {
                "id": None,
                "error": {
                    "code": 406,
                    "message": "Не определён родительский узел."
                }
            }

            self._logger.error((
                f"Попытка создания узла {data} "
                f"в неопределённом месте иерархии."
            ))

            return res

        if not self._check_parent_class(parent_node):
            res = {
                "id": None,
                "error": {
                    "code": 406,
                    "message": "Неприемлемый класс родительского узла."
                }
            }

            self._logger.error((
                f"Попытка создания узла {data} "
                f"в родительском узле неприемлемого класса."
            ))

            return res

        data["objectClass"] = self._config.hierarchy["class"]
        new_id = self._hierarchy.add(parent_node, data.get("attributes"))

        if not new_id:
            res = {
                "id": None,
                "error": {
                    "code": 406,
                    "message": "Ошибка создания узла."
                }
            }

            self._logger.error(f"Ошибка создания узла {data}")

        else:
            res = {
                "id": new_id,
                "error": {}
            }
            self._logger.info(f"Создан новый узел {new_id}")

        # при необходимости создадим узел ``system``
        if self._config.hierarchy["create_sys_node"]:
            await self._hierarchy.add(new_id, {"cn": ["system"]})

        await self._creating(data, new_id)

        await self._pub_exchange.publish(
            aio_pika.Message(
                body=f'{{"action": "created", "id": {new_id}}}'.encode(),
                content_type='application/json',
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=self._config.pub_exchange["routing_key"]
        )

        return res

    async def _creating(self, data: dict, new_id: str) -> None:
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

        if self._config.hierarchy["parent_classes"]:
            if (self._hierarchy.get_node_class(parent_id) in
                self._config.hierarchy["parent_classes"]):
                return True

        return False

    async def _check_hierarchy_node(self) -> None:
        """Метод проверяет наличие базового узла сущности и, в случае его
        отсутствия, создаёт его.
        """
        if not self._config.hierarchy["node_name"]:
            return

        item = await self._hierarchy.search(
            scope=CN_SCOPE_ONELEVEL,
            filter_str=f"(cn={self._config.hierarchy['node_name']})",
            attr_list=["entryUUID"]
        )
        if not item:
            base_node_id = await self._hierarchy.add(
                attr_vals={"cn": self._config.hierarchy["node_name"]}
            )

        self._config.hierarchy["node_dn"] = self._hierarchy.get_node_dn(base_node_id)
        self._config.hierarchy["node_id"] = base_node_id

    async def on_startup(self) -> None:
        """Метод, выполняемый при старте приложения:
        происходит проверка базового узла сущности.
        :py:func:`model_crud_svc.ModelCRUDSvc._check_hierarchy_node`
        """
        await super().on_startup()
        await self._check_hierarchy_node()
