import asyncio
from fastapi import FastAPI
import ldap

import aio_pika
import aio_pika.abc

from hierarchy import Hierarchy
from logger import PrsLogger
from src.common.settings import Settings

class Svc(FastAPI):
    """
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

        self.svc_name = settings.svc_name
        self.amqp_url = settings.amqp_url
        self.logger = PrsLogger.make_logger()
        self._hierarchy = Hierarchy(settings.ldap_url)

        self._amqp_connection: aio_pika.abc.AbstractRobustConnection = None
        self._svc_pub_channel: aio_pika.abc.AbstractRobustChannel = None
        self._svc_pub_exchange: aio_pika.abc.AbstractRobustExchange = None
        self._svc_pub_exchange_type = settings.pub_exchange_type

    async def _ldap_connect(self) -> None:
        """Функция соединения с ldap-сервером.
        В случае неудачи ошибка будет выведена в лог и попытки связи будут
        продолжаться с периодичностью в 5 секунд.

        Работа сервиса будет остановлена до тех пор, пока не установится
        связь.

        DSN для связи с ldap-сервером указывается в переменной окружения
        ``ldap_url``.

        Returns:
            None
        """
        try:
            self._hierarchy.connect()
        except ValueError:
            self.logger.error("Неверный формат URI ldap: {self.hierarchy.url}")
            await asyncio.sleep(5)
            return self._ldap_connect()

        except ldap.LDAPError as ex:
            self.logger.error(f"Ошибка связи с сервером ldap: {ex}")
            await asyncio.sleep(5)
            return self._ldap_connect()

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
        try:
            self._amqp_connection = await aio_pika.connect_robust(self.amqp_url)
            self._svc_pub_channel = await self._amqp_connection.channel()
            self._svc_pub_exchange = await self._svc_pub_channel.declare_exchange(
                self.svc_name, self._svc_pub_exchange_type,
            )
        except aio_pika.AMQPException as ex:
            self.logger.error(f"Ошибка связи с брокером: {ex}")
            await asyncio.sleep(5)
            return self._amqp_connect()

    async def on_startup(self) -> None:
        """Функция, выполняемая при старте сервиса: выполняется связь с
        ldap- и amqp-серверами.
        """
        await self._ldap_connect()
        await self._amqp_connect()

    async def on_shutdown(self) -> None:
        """Функция, выполняемая при остановке сервиса: разрывается связь
        с ldap- и amqp-серверами.
        """
        await self._svc_pub_channel.close()
        await self._amqp_connection.close()
