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
import re

import aio_pika
import aio_pika.abc
from aiormq.abc import DeliveredMessage
from pamqp.commands import Basic

from src.common.logger import PrsLogger
from src.common.base_svc_settings import BaseSvcSettings
#from src.common.local_cache import LocalCache
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

        self._logger.debug(f"{self._config.svc_name} :: Начало инициализации сервиса {settings.svc_name}.")

        if kwargs.get("on_startup"):
            kwargs.append(self.on_startup)
        else:
            kwargs["on_startup"] = [self.on_startup]
        if kwargs.get("on_shutdown"):
            kwargs.append(self.on_shutdown)
        else:
            kwargs["on_shutdown"] = [self.on_shutdown]

        super().__init__(*args, **kwargs)

        self._logger.debug(f"{self._config.svc_name} :: Смена петли событий...")

        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

        self._amqp_connection: aio_pika.abc.AbstractRobustConnection = None
        self._amqp_is_connected: bool = False
        self._amqp_channel: aio_pika.abc.AbstractRobustChannel = None
        self._exchange = aio_pika.abc.AbstractRobustExchange = None
        self._amqp_consume_queue: aio_pika.abc.AbstractRobustQueue = None
        self._amqp_callback_queue: aio_pika.abc.AbstractRobustQueue = None
        self._callback_futures: MutableMapping[str, asyncio.Future] = {}

        # Словарь {
        #   "re-pattern": function
        # }
        # Полагаемся на правило, введённое в Python 3.6 и подтверждённое для всех версий
        # >= 3.6 : порядок выборки ключей соответствует порядку их вставки.
        # Это нам нужно для того, что мы ищем первое соответствие ключа (регулярного выражения)
        # ключу маршрутазации сообщения. Как только будет найдено первое соответствие,
        # именно эта функция и будет вызвана для обработки сообщения.
        # Набор команд и функций определяется в каждом классе-наследнике.
        # Предполагается, что функция асинхронная, принимает на вход
        # пришедшее сообщение отдаёт и какой-то ответ, который будет переслан
        # обратно, если у сообщения выставлен параметр reply_to.
        # Список входящих команд переопределяется в специальной функции
        # _set_handlers, которая переписывается в каждом
        # классе-наследнике.

        self._handlers = {}
        self._set_handlers()
        self._cache = None

        self._initialized = False

    def _set_handlers(self):
        pass

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

    async def _check_mes_correctness(self, message: dict) -> bool:
        """Проверка корректности входящего сообщения.
        По умолчанию возвращает True.
        Переопределяется в классах-наследниках.

        Args:
            message (dict): Входящее сообщение

        Returns:
            bool: True, если сообщение корректно, False - в обратном случае.
        """
        return True

    async def _process_message(self, message: aio_pika.abc.AbstractIncomingMessage) -> None:
        """Метод обработки сообщений во всех очередях.
        Логика:
        1) Тело сообщения должно быть в формате json
        2) Проверяем на корректность тело сообщения
        3) Проверяем, надо ли вернуть сообщение в очередь
        4) Ищем первое соответствие routing_key сообщения ключу в словаре incoming_commands
           и вызываем соответствующую функцию.

        Args:
            message (aio_pika.abc.AbstractIncomingMessage): _description_
        """

        while not self._initialized:
            await asyncio.sleep(0.5)

        async with message.process(ignore_processed=True):
            mes = message.body.decode()

            correct = await self._check_mes_correctness(mes)
            if not correct:
                self._logger.error(f"{self._config.svc_name} :: Неправильный формат сообщения")
                await message.ack()
                return

            try:
                mes = json.loads(mes)
            except json.decoder.JSONDecodeError:
                self._logger.error(f"{self._config.svc_name} :: Сообщение {mes} не в формате json.")
                await message.ack()
                return
            
            reject = await self._reject_message(mes)
            if reject:
                self._logger.debug(f"{self._config.svc_name} :: Сообщение {mes} отклонено.")
                await message.reject(True)
                return

            # обработка сообщения
            passed = False
            for key in self._handlers.keys():
                if re.fullmatch(key, message.routing_key):
                    passed = True
                    res = await self._handlers[key](mes=mes, routing_key=message.routing_key)

                    if message.reply_to:
                        # здесь нельзя использовать self._post_message
                        await self._exchange.publish(
                            aio_pika.Message(
                                body=json.dumps(res,ensure_ascii=False).encode(),
                                correlation_id=message.correlation_id,
                            ),
                            routing_key=message.reply_to,
                        )
                    break

            if not passed:
                self._logger.warning(f"{self._config.svc_name} :: Сообщение с ключом {message.routing_key} не обработано.")
            
            await message.ack()

    async def _post_message(
            self, mes: dict, reply: bool = False, routing_key: str = None
    ) -> dict | bool | None:
        """Метод отсылает сообщение в брокер.

        Args:
            mes (dict): Тело сообщения
            reply (bool, optional): Флаг необходимости получения ответа на сообщение. Defaults to False.
            routing_key (str, optional): Ключ маршрутизации. Defaults to None.

        Returns:
            dict | bool | None: Возвращает ответ в виде словаря, если флаг reply = True, 
              None - если нет подписчика на посланное сообщение
              True - если reply = False и сообщение успешно отправлено.
        """

        body = json.dumps(mes, ensure_ascii=False).encode()
        correlation_id = None
        reply_to = None
        if reply:
            correlation_id = str(uuid4())
            reply_to = self._amqp_callback_queue.name
            
        if not routing_key:
            self._logger.error(f"{self._config.svc_name} :: Не указан routing_key для публикации сообщения.")
            return

        res = await self._exchange.publish(
            message=aio_pika.Message(
                body=body, correlation_id=correlation_id, reply_to=reply_to
            ), routing_key=routing_key
        )
        if isinstance(res, DeliveredMessage):
            if isinstance(res.delivery, Basic.Return):
                if res.delivery.reply_code == 312:
                    return
        if not reply:
            return True
        
        future = asyncio.get_running_loop().create_future()
        self._callback_futures[correlation_id] = future

        return await future

    async def _on_rpc_response(
            self, message: aio_pika.abc.AbstractIncomingMessage
    ) -> None:
        if message.correlation_id is None:
            self._logger.error(f"{self._config.svc_name} :: У сообщения не выставлен параметр `correlation_id`")
        else:
            try:
                future: asyncio.Future = self._callback_futures.pop(message.correlation_id, None)
                future.set_result(json.loads(message.body.decode()))
            except:
                self._logger.error(f"{self._config.svc_name} :: Ошибка работы с ответом.")

    async def _generate_queue(self):
        """Логика генерации очереди/очередей сообщений
        """
        self._amqp_consume_queue = await self._amqp_channel.declare_queue(
            f"{self._config.svc_name}_consume", durable=False, auto_delete=True
        )
        
    async def _bind_queue(self):
        for key in self._handlers.keys():
            await self._amqp_consume_queue.bind(exchange=self._exchange, routing_key=key)

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
                self._logger.debug(f"{self._config.svc_name} :: Установление связи с брокером сообщений...")
                self._amqp_connection = await aio_pika.connect_robust(self._config.broker["amqp_url"])
                self._amqp_channel = await self._amqp_connection.channel()
                await self._amqp_channel.set_qos(1)

                self._exchange = await self._amqp_channel.declare_exchange(
                    self._config.broker["name"], "topic", durable=False, auto_delete=True
                )

                await self._generate_queue()
                await self._bind_queue()
                                
                await self._amqp_consume_queue.consume(self._process_message)

                self._amqp_callback_queue = await self._amqp_channel.declare_queue(
                    durable=False, auto_delete=True, exclusive=True
                )
                await self._amqp_callback_queue.bind(
                    exchange=self._exchange,
                    routing_key=self._amqp_callback_queue.name
                )

                await self._amqp_callback_queue.consume(self._on_rpc_response, no_ack=True)

                self._logger.info(f"{self._config.svc_name}: Связь с AMQP сервером установлена.")

                self._initialized = True

            except aio_pika.AMQPException as ex:
                self._logger.error(f"{self._config.svc_name} :: Ошибка связи с брокером: {ex}")
                await asyncio.sleep(5)

    async def on_startup(self) -> None:
        """
        Функция, выполняемая при старте сервиса: выполняется связь с
        amqp-сервером.
        """
        self._logger.info(f"{self._config.svc_name} :: on_startup.")
        await self._amqp_connect()
        await self._cache_connect()        

    async def _cache_connect(self):
        #self._cache = LocalCache()
        self._cache = RedisCache(self._config.cache_url)

    async def on_shutdown(self) -> None:
        """
        Функция, выполняемая при остановке сервиса: разрывается связь
        с amqp-сервером.
        """
        await self._amqp_channel.close()
        await self._amqp_connection.close()
