"""
Модуль содержит базовый класс ``BaseSvc`` - предок классов-сервисов и класса Svc.
"""
import asyncio
from functools import cached_property
from fastapi import FastAPI

import aio_pika
import aio_pika.abc

from .logger import PrsLogger
from .settings import Settings


class BaseSvc(FastAPI):
    """
    Базовый класс ``BaseSvc`` - предок классов-сервисов и класса Svс,
    реализующего дополнительный функционал – соединение с ldap сервером.

    Выполняет одну задачу:

    * устанавливает связь с amqp-сервером и создаёт обменник для публикации
      сообщений.

    Args:
            settings (Settings): конфигурация приложения см. :class:`settings.Settings`
    """
    def __init__(self, settings: Settings, *args, **kwargs):
        if kwargs.get("on_startup"):
            kwargs.append(self.on_startup)
        else:
            kwargs["on_startup"] = [self.on_startup]
        if kwargs.get("on_shutdown"):
            kwargs.append(self.on_shutdown)
        else:
            kwargs["on_shutdown"] = [self.on_shutdown]

        super().__init__(*args, **kwargs)

        self._conf = settings
        self._logger = PrsLogger.make_logger(
            level=settings.log["level"],
            file_name=settings.log["file_name"],
            retention=settings.log["retention"],
            rotation=settings.log["rotation"]
        )
        self._amqp_connection: aio_pika.abc.AbstractRobustConnection = None
        self._amqp_channel: aio_pika.abc.AbstractRobustChannel = None
        self._pub_exchange: aio_pika.abc.AbstractRobustExchange = None

    @cached_property
    def _config(self):
        return self._conf
    
    async def _amqp_connect(self) -> None:
        """Функция связи с AMQP-сервером.
        Аналогично функции ldap-connect при неудаче ошибка будет выведена в лог
        и попытки связи будут продолжены с периодичностью в 5 секунд.

        DSN для связи с amqp-сервером указывается в переменной окружения
        ``amqp-url``.

        После установки соединения создаётся exchange с именем, указанным
        в переменной ``svc_name`` и типом, указанным в ``pub_exchange_type``.
        Именно этот exchange будет использоваться для публикации сообщений,
        генерируемых сервисом.

        Returns:
            None
        """
        connected = False
        while not connected:
            try:
                self._amqp_connection = await aio_pika.connect_robust(self._config.amqp_url)
                self._amqp_channel = await self._amqp_connection.channel()
                self._pub_exchange = await self._amqp_channel.declare_exchange(
                    self._config.pub_exchange["name"],
                    self._config.pub_exchange["type"], durable=True
                )
                connected = True

                self._logger.info("Связь с AMQP сервером установлена.")

            except aio_pika.AMQPException as ex:
                self._logger.error(f"Ошибка связи с брокером: {ex}")
                await asyncio.sleep(5)

    async def on_startup(self) -> None:
        """
        Функция, выполняемая при старте сервиса: выполняется связь с
        amqp-сервером.
        """
        await self._amqp_connect()

    async def on_shutdown(self) -> None:
        """
        Функция, выполняемая при остановке сервиса: разрывается связь
        с amqp-сервером.
        """
        await self._amqp_channel.close()
        await self._amqp_connection.close()
