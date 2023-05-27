"""
Модуль содержит базовый класс ``BaseSvc`` - предок классов-сервисов и класса Svc.
"""
import asyncio
from functools import cached_property
from fastapi import FastAPI

import aio_pika
import aio_pika.abc

from src.common.logger import PrsLogger
from src.common.base_svc_settings import BaseSvcSettings


class BaseSvc(FastAPI):
    """
    Kласс ``BaseSvc`` - предок классов-сервисов и класса Svс,
    реализующего дополнительный функционал – соединение с ldap сервером.

    Выполняет одну задачу:

    * устанавливает связь с amqp-сервером и создаёт обменник для публикации
      сообщений, а также, если указаны, очереди для потрбления сообщений

    После запуска эземпляр сервиса будет иметь следующие переменные:

    .. code:: python

        # кроме указанного в ключе "main", будут созданые другие обменники,
        # если они были описаны в конфигурации
        self._amqp_publish = {
            "main": exchange
        }

        # кроме указанных в ключе "main", будут созданые другие обменники и
        # очереди, если они были описаны в конфигурации
        self._amqp_consume = {
            "main": {
                "exchange": exchange,
                "queue": queue
            }
        }

    Args:
            settings (Settings): конфигурация приложения см. :class:`settings.Settings`
    """
    def __init__(self, settings: BaseSvcSettings, *args, **kwargs):
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
        self._amqp_publish: dict = None
        self._amqp_consume: dict = None

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

                for key, item in self._config.publish.items():
                    self._amqp_publish[key] = await self._amqp_channel.declare_exchange(
                        item["name"], item["type"], durable=True
                    )
                for key, item in self._config.consume.items():
                    self._amqp_consume[key] = {}
                    self._amqp_consume[key]["exchange"] = (
                        await self._amqp_channel.declare_exchange(
                            item["name"], item["type"], durable=True
                        )
                    )
                    self._amqp_consume[key]["queue"] = (
                        await self._amqp_channel.declare_queue(
                            item["queue_name"], durable=True
                        )
                    )
                    await self._amqp_consume[key]["queue"].bind(
                        exchange=self._amqp_consume[key]["exchange"],
                        routing_key=item["routing_key"]
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
