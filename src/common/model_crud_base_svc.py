# базовый класс для управления экземплярами сущностей в иерархии
# по умолчанию, каждая сущность может иметь "свой" узел в иерархрии
# для создания в нём "своей" иерархии; но это необязательно
from typing import Annotated
import asyncio
import json

import aio_pika
import aio_pika.abc

from base_svc import BaseService
from crud_settings import CRUDSettings

class BaseModelCRUD(BaseService):
    """Базовый класс для всех сервисов, работающих с экземплярами сущностей
    в иерархической модели. При запуске подписывается на сообщения
    exchange'а с именем, задаваемым в переменной ``api_crud_exchange``,
    создавая очередь ``api_crud_queue``.
    Сообщения, приходящие в эту очередь, создаются сервисом API_CRUD.
    Часть сообщений эмулируют RPC, у них параметр ``reply_to`` содержит имя
    очереди, в которую нужно отдать результат.
    Это сообщения: создание, поиск. Другие же сообщения (update, delete)
    не предполагают ответа.

    Args:
        BaseService (_type_): _description_
    """

    def __init__(self, settings: CRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

        self._api_crud_exchange_name : str = settings.api_crud_exchange
        self._api_crud_queue_name : str = settings.api_crud_queue
        self.hierarchy_node : str = settings.hierarchy_node

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
        await self._svc_consume_queue.consume(self.process_message)
        await asyncio.Future()

    async def process_message(self,
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
                res = await self.create(mes)
            elif action == "update":
                res = await self.update(mes)
            elif action == "read":
                res = await self.read(mes)
            elif action == "delete":
                res = await self.delete(mes)
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

    async def create(self, mes) -> dict:
        pass


    async def check_hierarchy_node(self) -> None:
        if not self.hierarchy_node:
            return

        item = await self._hierarchy.search(filter_str=f"(cn={self.hierarchy_node})", attr_list=["entryUUID"])
        if item:
            return

        await self._hierarchy.add(attr_vals={"cn": self.hierarchy_node})

    async def on_startup(self) -> None:
        await super().on_startup()
        await self.check_hierarchy_node()
