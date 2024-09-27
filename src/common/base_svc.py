"""
Модуль содержит базовый класс ``BaseSvc`` - предок классов-сервисов и класса Svc.
"""
import json
import asyncio
import uvloop
from functools import cached_property
from uuid import uuid4
from collections.abc import MutableMapping
from fastapi import FastAPI

import aio_pika
import aio_pika.abc

from src.common.logger import PrsLogger
from src.common.base_svc_settings import BaseSvcSettings
from src.common.redis_cache import RedisCache

class BaseSvc(FastAPI):
    
    def __init__(self, settings: BaseSvcSettings, *args, **kwargs):

        self._conf = settings
        self._logger = PrsLogger.make_logger(
            level=settings.log["level"],
            file_name=settings.log["file_name"],
            retention=settings.log["retention"],
            rotation=settings.log["rotation"]
        )

        self._logger.debug(f"Начало инициализации сервиса {settings.svc_name}.")

        if kwargs.get("on_startup"):
            kwargs.append(self.on_startup)
        else:
            kwargs["on_startup"] = [self.on_startup]
        if kwargs.get("on_shutdown"):
            kwargs.append(self.on_shutdown)
        else:
            kwargs["on_shutdown"] = [self.on_shutdown]

        super().__init__(*args, **kwargs)

        self._logger.debug("Смена петли событий...")

        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

        self._amqp_connection: aio_pika.abc.AbstractRobustConnection = None
        self._amqp_is_connected: bool = False
        self._amqp_channel: aio_pika.abc.AbstractRobustChannel = None
        self._amqp_publish: None
        self._amqp_consume: dict = {
            "queue": None,
            "exchange": None
        }
        self._amqp_callback_queue: aio_pika.abc.AbstractRobustQueue = None
        self._callback_futures: MutableMapping[str, asyncio.Future] = {}

        # Словарь {
        #   "<action>": function
        # }
        # используется для вызова соответствующей функции при получении
        # определённого сообщения.
        # Набор команд и функций определяется в каждом классе-наследнике.
        # Предполагается, что функция асинхронная, принимает на вход
        # пришедшее сообщение отдаёт и какой-то ответ, который будет переслан
        # обратно, если у сообщения выставлен параметр reply_to.
        # Список входящих команд переопределяется в специальной функции
        # _set_incoming_commands, которая переписывается в каждом
        # классе-наследнике. 
        self._incoming_commands = self._set_incoming_commands()
        self._outgoing_commands = self._set_outgoing_commands()

        self._cache = None

        self._initialized = False

    def _set_incoming_commands(self) -> dict:
        return {}

    def _set_outgoing_commands(self) -> dict:
        return {}

    @cached_property
    def _config(self):
        return self._conf

    async def _reject_message(self, mes: dict) -> bool:
        """Проверка сообщения на предмет того, что оно предназначается
        данному сервису.
        Метод может быть переопределён в сервисах-потомках.

        Args:
            mes (dict): _description_

        Returns:
            bool: True - сообщение возвращается в очередь;
                  False - сообщение обрабатывается сервисом.
        """

        return False

    async def _check_mes_correctness(self, message: aio_pika.abc.AbstractIncomingMessage) -> bool:
        return True

    async def _process_message(self, message: aio_pika.abc.AbstractIncomingMessage) -> None:

        while not self._initialized:
            await asyncio.sleep(0.5)

        correct = await self._check_mes_correctness(message)
        if not correct:
            self._logger.error(f"Неправильный формат сообщения")
            await message.ack()
            return

        async with message.process(ignore_processed=True):
            mes = message.body.decode()

            try:
                mes = json.loads(mes)
            except json.decoder.JSONDecodeError:
                self._logger.error(f"Сообщение {mes} не в формате json.")
                await message.ack()
                return

            if not mes.get("action"):
                self._logger.error(f"В сообщении {mes} не указано действие.")
                await message.ack()
                return
            #mes["action"] = mes["action"].lower()
            if not mes["action"] in self._incoming_commands.keys():
                self._logger.error(f"Сервис `{self._config.svc_name}`. Неизвестное действие {mes['action']}.")
                await message.ack()
                return

            reject = await self._reject_message(mes)
            if reject:
                self._logger.debug(f"Сообщение {mes} отклонено.")
                await message.reject(True)
                return

            func = self._incoming_commands.get(mes["action"])

            res = await func(mes)

            if not message.reply_to:
                await message.ack()
                return

            await self._amqp_consume["exchanges"]["main"]["exchange"].publish(
                aio_pika.Message(
                    body=json.dumps(res,ensure_ascii=False).encode(),
                    correlation_id=message.correlation_id,
                ),
                routing_key=message.reply_to,
            )
            await message.ack()

    async def _post_message(
            self, mes: dict, reply: bool = False, routing_key: str = None
    ) -> dict | None:

        body = json.dumps(mes, ensure_ascii=False).encode()
        correlation_id = None
        reply_to = None
        if reply:
            correlation_id = str(uuid4())
            reply_to = self._amqp_callback_queue.name
            future = asyncio.get_running_loop().create_future()
            self._callback_futures[correlation_id] = future

        if not routing_key:
            routing_key = self._config.publish["main"]["routing_key"]

        await self._amqp_publish["main"]["exchange"].publish(
            message=aio_pika.Message(
                body=body, correlation_id=correlation_id, reply_to=reply_to
            ), routing_key=routing_key
        )
        if not reply:
            return

        return await future

    async def _on_rpc_response(
            self, message: aio_pika.abc.AbstractIncomingMessage
    ) -> None:
        if message.correlation_id is None:
            self._logger.error("У сообщения не выставлен параметр `correlation_id`")
        else:
            future: asyncio.Future = self._callback_futures.pop(message.correlation_id, None)
            future.set_result(json.loads(message.body.decode()))

    async def _bind_for_consume(self):
        pass

    async def _amqp_connect(self) -> None:
        """Функция связи с AMQP-сервером.
        Аналогично функции ldap-connect при неудаче ошибка будет выведена в лог
        и попытки связи будут продолжены с периодичностью в 5 секунд.

        DSN для связи с amqp-сервером указывается в переменной окружения
        ``amqp-url``\.

        После установки соединения создаётся exchange с именем, указанным
        в переменной ``svc_name`` и типом, указанным в ``pub_exchange_type``\.
        Именно этот exchange будет использоваться для публикации сообщений,
        генерируемых сервисом.

        Также создаётся очередь для ответов RPC.

        Returns:
            None
        """
        while not self._initialized:
            try:
                self._logger.debug("Установление связи с брокером сообщений...")
                self._amqp_connection = await aio_pika.connect_robust(self._config.amqp_url)
                self._amqp_channel = await self._amqp_connection.channel()
                await self._amqp_channel.set_qos(1)

                self._amqp_publish = await self._amqp_channel.declare_exchange(
                    self._config.publish["name"], self._config.publish["type"], durable=True
                )

                self._amqp_consume["queue"] = \
                    await self._amqp_channel.declare_queue(
                        self._config.consume["queue_name"], durable=True
                    )
                self._amqp_consume["exchange"] = (
                    await self._amqp_channel.declare_exchange(
                        self._config.consume["name"], self._config.consume["type"], durable=True
                    )
                )
                r_ks = self._config.consume.get("routing_key")
                if r_ks:
                    if not isinstance(r_ks, list):
                        r_ks = [r_ks]
                    for r_k in r_ks:
                        await self._amqp_consume["queue"].bind(
                            exchange=self._amqp_consume["exchange"],
                            routing_key=r_k
                        )
                else:
                    await self._bind_for_consume()

                await self._amqp_consume["queue"].consume(self._process_message)

                self._amqp_callback_queue = await self._amqp_channel.declare_queue(
                    durable=True, exclusive=True
                )
                await self._amqp_callback_queue.bind(
                    exchange=self._amqp_publish["main"]["exchange"],
                    routing_key=self._amqp_callback_queue.name
                )

                await self._amqp_callback_queue.consume(self._on_rpc_response, no_ack=True)

                self._logger.info(f"{self._config.svc_name}: Связь с AMQP сервером установлена.")

                self._initialized = True

            except aio_pika.AMQPException as ex:
                self._logger.error(f"Ошибка связи с брокером: {ex}")
                await asyncio.sleep(5)

    async def on_startup(self) -> None:
        """
        Функция, выполняемая при старте сервиса: выполняется связь с
        amqp-сервером.
        """
        self._logger.info(f"{self._config.svc_name}: on_startup.")
        await self._amqp_connect()

        await self._cache_connect()

    async def _cache_connect(self):
        self._cache = RedisCache(self._config.cache_url)

    async def on_shutdown(self) -> None:
        """
        Функция, выполняемая при остановке сервиса: разрывается связь
        с amqp-сервером.
        """
        await self._amqp_channel.close()
        await self._amqp_connection.close()
