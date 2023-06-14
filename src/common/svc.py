"""
Модуль содержит базовый класс ``Svc`` - предок всех сервисов.
"""
import asyncio
from functools import cached_property
import ldap

import aio_pika
import aio_pika.abc

from src.common.hierarchy import Hierarchy
from src.common.svc_settings import SvcSettings
from src.common.base_svc import BaseSvc


class Svc(BaseSvc):
    """
    Базовый класс ``Svc`` - предок классов-сервисов.

    Выполняет две задачи:

    * устанавливает связь с ldap-сервером;
    * устанавливает связь с amqp-сервером и создаёт обменник для публикации
      сообщений.

    Args:
            settings (Settings): конфигурация приложения см. :class:`settings.Settings`
    """

    def __init__(self, settings: SvcSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)
        self._hierarchy = Hierarchy(settings.ldap_url)
        self._amqp_subscribe = {}

    async def _ldap_connect(self) -> None:
        """
        Функция соединения с ldap-сервером.
        В случае неудачи ошибка будет выведена в лог и попытки связи будут
        продолжаться с периодичностью в 5 секунд.

        Работа сервиса будет остановлена до тех пор, пока не установится
        связь.

        DSN для связи с ldap-сервером указывается в переменной окружения
        ``ldap_url``.

        Returns:
            None
        """
        connected = False
        while not connected:
            try:
                self._hierarchy.connect()
                connected = True
                self._logger.info("Связь с LDAP сервером установлена.")
            except ValueError:
                self._logger.error(f"Неверный формат URI ldap: {self._config.ldap_url}")
                await asyncio.sleep(5)

            except ldap.LDAPError as ex:
                self._logger.error(f"Ошибка связи с сервером ldap: {ex}")
                await asyncio.sleep(5)

    async def _amqp_connect(self) -> None:
        await super()._amqp_connect()

        # создадим подписки
        for key, item in self._config.subscribe.items():
            self._amqp_subscribe[key] = {
                "publish": {},
                "consume": {}
            }

            # сюда будем публиковать заявки на уведомления
            self._amqp_subscribe[key]["publish"]["exchange"] = \
                await self._amqp_channel.declare_exchange(
                    item["publish"]["name"], item["publish"]["type"], durable=True
            )
            self._amqp_subscribe[key]["publish"]["routing_key"] = \
                item["publish"]["routing_key"]

            # для получения уведомлений подсоединим свою главную очередь
            self._amqp_subscribe[key]["consume"]["exchange"] = \
                await self._amqp_channel.declare_exchange(
                    item["consume"]["name"], item["consume"]["type"], durable=True
            )
            await self._amqp_consume[key]["queue"].bind(
                exchange=self._amqp_subscribe[key]["consume"]["exchange"],
                routing_key=self._amqp_subscribe[key]["consume"]["routing_key"]
            )

    async def on_startup(self) -> None:
        await super().on_startup()
        await self._ldap_connect()
