# базовый класс для управления экземплярами сущностей в иерархии
# по умолчанию, каждая сущность может иметь "свой" узел в иерархрии
# для создания в нём "своей" иерархии; но это необязательно
from typing import Annotated, Any, List
import asyncio
import json

import aio_pika
import aio_pika.abc

from hierarchy import CN_SCOPE_ONELEVEL, CN_SCOPE_SUBTREE
from src.common.svc import BaseService
from src.common.crud_settings import CRUDSvcSettings

class BaseModelCRUD(BaseService):
    """Базовый класс для всех сервисов, работающих с экземплярами сущностей
    в иерархической модели.

    При запуске подписывается на сообщения
    exchange'а с именем, задаваемым в переменной ``api_crud_exchange``,
    создавая очередь ``api_crud_queue``.

    Сообщения, приходящие в эту очередь, создаются сервисом API_CRUD.
    Часть сообщений эмулируют RPC, у них параметр ``reply_to`` содержит имя
    очереди, в которую нужно отдать результат.
    Это сообщения: создание, поиск. Другие же сообщения (update, delete)
    не предполагают ответа.
    """

    def __init__(self, settings: CRUDSvcSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

        self._api_crud_exchange_name : str = settings.api_crud_exchange
        self._api_crud_queue_name : str = settings.api_crud_queue

        self.hierarchy_node : str = settings.hierarchy_node
        self.hierarchy_class : str = settings.hierarchy_class
        self.hierarchy_parent_class : str = None

        self._svc_consume_channel: aio_pika.abc.AbstractRobustChannel = None
        self._svc_consume_exchange: aio_pika.abc.AbstractRobustExchange = None
        self._svc_consume_queue: aio_pika.abc.AbstractRobustQueue = None

    async def _amqp_connect(self) -> None:
        await super()._amqp_connect()

        self._svc_consume_channel = await self._amqp_connection.channel()
        self._svc_consume_exchange = await self._svc_consume_channel.declare_exchange(
            self._api_crud_exchange_name, aio_pika.ExchangeType.FANOUT,
        )
        self._svc_consume_queue = await self._svc_consume_channel.declare_queue(
            self._api_crud_queue_name, durable=True
        )
        await self._svc_consume_queue.bind(exchange=self._svc_consume_exchange)
        await self._svc_consume_queue.consume(self._process_message)
        await asyncio.Future()

    async def _process_message(self,
            message: aio_pika.abc.AbstractIncomingMessage
    ) -> None:
        async with message.process(ignore_processed=True):
            mes = message.body.decode()
            try:
                mes = json.loads(mes)
            except json.decoder.JSONDecodeError:
                self.logger.error(f"Сообщение {mes} не в формате json.")
                await message.ack()
                return

            action = mes.get("action")
            if not action:
                self.logger.error(f"В сообщении {mes} не указано действие.")
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
                self.logger.error(f"Неизвестное действие: {action}.")
                await message.ack()
                return

            if not message.reply_to:
                await message.ack()
                return

            await self._svc_consume_exchange.publish(
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
                self.logger.error("Неправильный класс нового родительского узла.")
                return

        self._hierarchy.modify(data["id"], data["attributes"])
        self._updating(data)
        await self._svc_pub_exchange.publish(
            aio_pika.Message(
                body=f'{{"action": "updated", "id": {data["id"]}}}'.encode(),
                content_type='application/json',
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key="*"
        )
        self.logger.info(f'Узел {data["id"]} обновлён.')

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

        await self._svc_pub_exchange.publish(
            aio_pika.Message(
                body=f'{{"action": "deleted", "id": {ids}}}'.encode(),
                content_type='application/json',
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key="*"
        )
        self.logger.info(f'Узлы {ids} удалены.')

    async def _deleting(self, ids: List[str]) -> None:
        """Метод переопределяется в сервисах-наследниках.
        Используется для выполнения специфической работы при удалении
        экземпляра сущности.

        Вызывается методом ``delete`` после удаления узла в иерархии, но
        перед посылкой сообщения об удалении в очередь.

        Args:
            ids (List[str]): список ``id`` удаляемых узлов.
        """

    async def _read(
        self, base: str = None, filter_str: str = None,
        scope: Any = CN_SCOPE_SUBTREE, attr_list: list[str] = None) -> tuple:
        return self._hierarchy.search(
            base=base, filter_str=filter_str, scope=scope, attr_list=attr_list
        )

    async def _create(self, data: dict) -> dict:
        """Метод создаёт новый экземпляр сущности в иерархии.

        Args:
            data (dict): входные данные вида:
                {
                    "parentId": <id родителя>,
                    "attributes": {
                        <ldap-attribute>: <value>
                    }
                }
                ``parentId`` - id родительской сущности; в случае, если = None,
                    то экзмепляр создаётся внутри базового для данной сущности
                    узла; если ``parentId`` = None и нет базового узла, то
                    генерируется ошибка.

        Returns:
            dict: {"id": <new_id>}
        """

        parent_node = data.get("parentId")
        parent_node = parent_node if parent_node else self.hierarchy_node
        if not parent_node:
            res = {
                "id": None,
                "error": {
                    "code": 406,
                    "message": "Не указан родительский узел."
                }
            }
            return res

        if not self._check_parent_class(data["parentId"]):
            res = {
                "id": None,
                "error": {
                    "code": 406,
                    "message": "Неприемлемый класс родительского узла."
                }
            }
            return res

        new_id = self._hierarchy.add(parent_node, data.get("attributes"))

        if not new_id:
            res = {
                "id": None,
                "error": {
                    "code": 406,
                    "message": "Ошибка создания узла."
                }
            }
        else:
            res = {
                "id": new_id,
                "error": {}
            }

        await self._creating(data, new_id)

        await self._svc_pub_exchange.publish(
            aio_pika.Message(
                body=f'{{"action": "created", "id": {new_id}}}'.encode(),
                content_type='application/json',
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key="*"
        )

        return res

    async def _creating(self, data: dict, new_id: str) -> None:
        """Метод переопределяется в сервисах-наследниках.
        В этом методе содержится специфическая работа при создании
        нового экземпляра сущности.

        Метод вызывается методом ``create`` после создания узла в иерархии,
        но перед посылкой сообщения о создании в очередь.

        Args:
            data (dict): атрибуты вновь создаваемого экземпляра сущности
            new_id (str): id уже созданного узла
        """

    async def _check_parent_class(self, parent_id: str) -> bool:
        """Метод проверки того, что класс родительского узла
        соответсвует необходимому. К примеру, тревоги могут создаваться только
        внутри тегов. То есть при создании новой тревоги мы должны убедиться,
        что класс родительского узла - ``prsTag``.

        Метод должен быть переопределён в классах-наследниках.

        Args:
            parent_id (str): идентификатор родительского узла

        Returns:
            bool: _description_
        """
        return True

    async def update(self, data) -> None:
        await self._hierarchy.modify(data["id"], data["attributes"])

    async def check_hierarchy_node(self) -> None:
        if not self.hierarchy_node:
            return

        item = await self._hierarchy.search(scope=CN_SCOPE_ONELEVEL, filter_str=f"(cn={self.hierarchy_node})", attr_list=["entryUUID"])
        if item:
            return

        await self._hierarchy.add(attr_vals={"cn": self.hierarchy_node})

    async def on_startup(self) -> None:
        await super().on_startup()
        await self.check_hierarchy_node()
