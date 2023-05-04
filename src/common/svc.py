import asyncio
from fastapi import FastAPI
import ldapurl
import ldap
from ldappool import ConnectionManager

import aio_pika
import aio_pika.abc

from src.common.settings import Settings
from hierarchy import Hierarchy
from logger import PrsLogger

class Svc(FastAPI):
    """Базовый класс для сервисов.
    Соединяется с AMQP, создаёт exchange типа директ со своим именем.

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
        await self._ldap_connect()
        await self._amqp_connect()

    async def on_shutdown(self) -> None:
        await self._svc_pub_channel.close()
        await self._amqp_connection.close()
