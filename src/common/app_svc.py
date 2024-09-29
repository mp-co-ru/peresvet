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
from src.common.svc import Svc


class AppSvc(Svc):
    """
    Класс ``Svc`` - наследник класса :class:`BaseSvc`

    Реализует дополнительную функциональность:

    * коннект к иерархии;
    * логика подписок на сообщения между сервисами.

    Args:
            settings (Settings): конфигурация приложения см. :class:`~svc_settings.SvcSettings`
    """

    def __init__(self, settings: SvcSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)
        self._hierarchy = Hierarchy(settings.ldap_url)

    async def on_startup(self) -> None:
        await super().on_startup()
        await self._ldap_connect()

    def _set_incoming_commands(self) -> dict:
        return {
            f"{self._config.hierarchy['class']}.model.created.*": self._created,
            f"{self._config.hierarchy['class']}.model.mayUpdate.*": self._mayUpdate,
            f"{self._config.hierarchy['class']}.model.updating.*": self._updating,
            f"{self._config.hierarchy['class']}.model.mayDelete.*": self._mayDelete,
            f"{self._config.hierarchy['class']}.model.deleting.*": self._deleting,
            f"{self._config.hierarchy['class']}.app_api.*": self._messages_from_app_api
        }

    async def _created(self,mes):
        pass

    async def _mayUpdate(self,mes):
        return {"response": True}
    
    async def _updating(self,mes):
        return {"response": True}
    
    async def _mayDelete(self,mes):
        return {"response": True}

    async def _deleting(self,mes):
        return {"response": True}
    
    async def _messages_from_app_api(self,mes):
        return

    