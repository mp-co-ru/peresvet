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

    def _set_handlers(self):

        if not self._config.nodes:
            self._handlers[f"{self._config.hierarchy['class']}.model.created"] = self._created
            self._handlers[f"{self._config.hierarchy['class']}.model.may_update.*"] = self._may_update
            self._handlers[f"{self._config.hierarchy['class']}.model.updating.*"] = self._updating
            self._handlers[f"{self._config.hierarchy['class']}.model.updated.*"] = self._updated
            self._handlers[f"{self._config.hierarchy['class']}.model.may_delete.*"] = self._may_delete
            self._handlers[f"{self._config.hierarchy['class']}.model.deleting.*"] = self._deleting
            self._handlers[f"{self._config.hierarchy['class']}.model.deleted.*"] = self._deleted
        else:
            for node in self._config.nodes:
                self._handlers[f"{self._config.hierarchy['class']}.model.may_update.{node}"] = self._may_update
                self._handlers[f"{self._config.hierarchy['class']}.model.updating.{node}"] = self._updating
                self._handlers[f"{self._config.hierarchy['class']}.model.updated.{node}"] = self._updated
                self._handlers[f"{self._config.hierarchy['class']}.model.may_delete.{node}"] = self._may_delete
                self._handlers[f"{self._config.hierarchy['class']}.model.deleting.{node}"] = self._deleting
                self._handlers[f"{self._config.hierarchy['class']}.model.deleted.{node}"] = self._deleted

        self._add_app_handlers()
        
    def _add_app_handlers(self):
        #self._handlers[f"{self._config.hierarchy['class']}.app_api.*"] = self._messages_from_app_api
        pass
    
    async def _generate_queue(self):
        if not self._config.nodes:
            await super()._generate_queue()
            return
        
        self._amqp_consume_queue = await self._amqp_channel.declare_queue(
            f"{self._config.svc_name}_consume_{self._config.nodes[0]}", durable=False, auto_delete=True
        )

    async def _created(self, mes: dict, routing_key: str = None):
        pass
        
    async def _may_update(self, mes: dict, routing_key: str = None):
        return {"response": True}
    
    async def _updating(self, mes: dict, routing_key: str = None):
        return {"response": True}
    
    async def _updated(self, mes: dict, routing_key: str = None):
        return {"response": True}
    
    async def _may_delete(self, mes: dict, routing_key: str = None):
        return {"response": True}

    async def _deleting(self, mes: dict, routing_key: str = None):
        return {"response": True}
      
    async def _deleted(self, mes: dict, routing_key: str = None):
        return {"response": True}
    