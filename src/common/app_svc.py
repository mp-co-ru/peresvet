"""
Модуль содержит базовый класс ``Svc`` - предок всех сервисов.
"""
from uuid import uuid4

from src.common.hierarchy import Hierarchy
from src.common.app_svc_settings import AppSvcSettings
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

    def __init__(self, settings: AppSvcSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)
        self._hierarchy = Hierarchy(settings.ldap_url)

    async def on_startup(self) -> None:
        await super().on_startup()
        await self._ldap_connect()

    def _set_handlers(self):

        if not self._config.nodes:
            self._handlers[f"{self._config.hierarchy['class']}.model.created"] = self._created
            self._handlers[f"{self._config.hierarchy['class']}.model.mayUpdate.*"] = self._mayUpdate
            self._handlers[f"{self._config.hierarchy['class']}.model.updating.*"] = self._updating
            self._handlers[f"{self._config.hierarchy['class']}.model.mayDelete.*"] = self._mayDelete
            self._handlers[f"{self._config.hierarchy['class']}.model.deleting.*"] = self._deleting
        else:
            for node in self._config.nodes:
                self._handlers[f"{self._config.hierarchy['class']}.model.mayUpdate.{node}"] = self._mayUpdate
                self._handlers[f"{self._config.hierarchy['class']}.model.updating.{node}"] = self._updating
                self._handlers[f"{self._config.hierarchy['class']}.model.mayDelete.{node}"] = self._mayDelete
                self._handlers[f"{self._config.hierarchy['class']}.model.deleting.{node}"] = self._deleting

        self._add_app_handlers()
        
    def _add_app_handlers(self):
        self._handlers[f"{self._config.hierarchy['class']}.app_api.*"] = self._messages_from_app_api
    
    async def _generate_queue(self):
        if not self._config.nodes:
            await super()._generate_queue()
            return
        
        self._amqp_consume_queue = await self._amqp_channel.declare_queue(
            f"{self._config.svc_name}_consume_{self._config.nodes[0]}", durable=True
        )

    async def _created(self, mes):
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

    