"""
Модуль содержит классы, описывающие входные данные для команд CRUD для тегов
и класс сервиса ``methods_api_crud_svc``\.
"""
import sys
import json
from patio import NullExecutor, Registry
from patio_rabbitmq import RabbitMQBroker

sys.path.append(".")

from src.common.app_svc import AppSvc
from src.common.hierarchy import CN_SCOPE_ONELEVEL
from src.services.methods.app.methods_app_settings import MethodsAppSettings

class MethodsApp(AppSvc):
    """
    Сервис работы с методами.
    Формат ожидаемых сообщений

    Приложение формирует два типа кэша:
    1) <initiator_id>.methods_app = 
        {
            "<method_id>": "<tag_id>"
        }
    2) <method_id>.methods_app = [
            "<initiator_id1>", "<initiator_id2>"
        ]

    """

    def __init__(self, settings: MethodsAppSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)
        self._method_broker = None
        self._rpc_executor = None
        self._rpc_exchange = None

    def _add_app_handlers(self):
        self._handlers["prsTag.app.data_set.*"] = self._start_method_by_sched
        #self._handlers["prsTag.model.updated.*"] = self._tag_updated
        self._handlers["prsSchedule.app.fire_event.*"] = self._start_method_by_tag

    '''
    async def _tag_updated(self, mes: dict):
        # если тег становится неактивным, отписываемся от событий 
        # инициаторов

        # получим флаг активности тега
        payload = {
            "id": mes['id'],
            "attributes": ["prsActive"]
        }
        tag_active = await self._hierarchy.search(payload=payload)
        if not tag_active:
            self._logger.error(f"{self._config.svc_name} :: Тег '{mes['id']}' отсутствует в модели.")
            return
        tag_active = tag_active[0][2]["prsActive"][0] == 'TRUE'

        # получим список всех методов под тегом 
        payload = {
            "base": mes['id'],
            # пока работаем только с методами тега, но, в общем случае,
            # под тегом есть алерты и у них тоже методы
            # по идее, при деактивации тега нужно отписывать и их
            # TODO: реализовать вышеописанное
            "scope": CN_SCOPE_ONELEVEL, 
            "filter": {
                "objectClass": ["prsMethod"]
            },
            "attributes": ["cn"]
        }
        methods = await self._hierarchy.search(payload=payload)
        if not methods:
            self._logger.error(f"{self._config.svc_name} :: Не обнаружено привязанных к тегу '{mes['id']}' методов.")
            return

        for method in methods:
            if tag_active:
                self.
    '''

    async def _start_method_by_sched(self, mes: dict) -> dict:
        self._logger.debug(f"Run methods. Data: {mes}")

        """
        {
            "id": sched_id,
            "time": x
        }
        """
        # TODO: практически повторение следующего метода. объединить

        initiator = mes["id"]
        methods_ids = await self._cache.get(f"{initiator}.{self._config.svc_name}").exec()
        if not methods_ids[0]:
            self._logger.error(f"{self._config.svc_name} :: К тегу '{initiator}' не привязаны методы.")
            return

        """
        methods_ids = [
            {
                "methodId": "...",
                "tagId": "..."
            }
        ]
        """
        self._logger.debug(f"{self._config.svc_name} :: methods_ids: {methods_ids[0]}")
        for item in methods_ids[0]:
            parameters = await self._hierarchy.search({
                "base": item["methodId"],
                "filter": {"cn": ["*"], "objectClass": ["prsMethodParameter"]},
                "attributes": ["prsJsonConfigString", "prsIndex", "cn"]
            })
            await self._calc_tag(item["tagId"], item["methodId"], parameters, [None, mes['time'], None])

    async def _start_method_by_tag(self, mes: dict) -> dict:

        self._logger.debug(f"Run methods. Data: {mes}")

        """
        {
            "data": [
                tag_item
            ]            
        }
        """

        for tag_item in mes["data"]:
            tag_id = tag_item["tagId"]
            tag_data = tag_item["data"]
            methods_ids = await self._cache.get(f"{tag_id}.{self._config.svc_name}").exec()
            if not methods_ids[0]:
                self._logger.error(f"{self._config.svc_name} :: К тегу '{tag_id}' не привязаны методы.")
                continue

            """
            methods_ids = [
                {
                    "methodId": "...",
                    "tagId": "..."
                }
            ]
            """
            self._logger.debug(f"methods_ids: {methods_ids[0]}")
            for item in methods_ids[0]:
                parameters = await self._hierarchy.search({
                    "base": item["methodId"],
                    "filter": {"cn": ["*"], "objectClass": ["prsMethodParameter"]},
                    "attributes": ["prsJsonConfigString", "prsIndex", "cn"]
                })
                for tag_data_item in tag_data:
                    await self._calc_tag(item["tagId"], item["methodId"], parameters, tag_data_item)

    async def _calc_tag(self, tag_id: str, method_id: str, parameters: dict, data: list[int | None]) -> None:

        self._logger.debug(f"calc_tag. tag_id: {tag_id}; method_id: {method_id}; parameters: {parameters}; data: {data}")

        parameters_data = []
        for parameter in parameters:
            request = json.loads(parameter[2]["prsJsonConfigString"][0])

            request["finish"] = data[1]
            
            self._logger.debug(f"mes: {request}")

            param_data = await self._post_message(
                mes=request,
                reply=True,
                routing_key=f"prsTag.app_api_client.data_get.*"
            )
            if parameter[2]["prsIndex"][0] is None:
                index = None
            else:
                index = int(parameter[2]["prsIndex"][0])
            parameters_data.append(
                {
                    "index": index,
                    "data": param_data
                }
            )

        self._logger.debug(f"Parameters data: {parameters_data}")

        parameters_data.sort(key=lambda item: (item["index"], 1000)[item["index"] is None])
        params_data = [item["data"] for item in parameters_data]

        method_name = await self._hierarchy.search(
            {
                "id": method_id,
                "attributes": ["prsMethodAddress"]
            }
        )

        self._logger.debug(f"Before call: method_id: {method_id}; method_name: {method_name}")

        try:
            res = await self._rpc_exchange.call(method_name[0][2]["prsMethodAddress"][0], *params_data)
            if isinstance(res, dict) and res.get("error") is not None:
                self._logger.error(f"{self._config.svc_name} :: Ошибка при вычислении тега {tag_id}: {res.get('error')}")
                return

            self._logger.debug(f"Результат: {res}. Тег: {tag_id}")

        except Exception as ex:
            self._logger.error(f"{self._config.svc_name} :: Критическая ошибка при вычислении тега {tag_id}: {ex}")
            return

        await self._post_message(mes={
            "data": [
                {
                    "tagId": tag_id,
                    "data": [
                        (res, data[1], None)
                    ]
                }
            ]            
        }, reply=False, routing_key=f"prsTag.app_api_client.data_set.{tag_id}")

    async def _deleting(self, mes):
        # перед удалением тревоги
        await self._delete_method_cache(mes['id'])
        await self._unbind_method(mes['id'])

    async def _bind_method(self, method_id: str):
        # только логика привязки
        # проверка активности метода производится вызывающим методом
        # привязка к сообщениям prsMethod.model.* выполняется при старте сервиса и здесь не меняется
        base = await self._hierarchy.get_node_dn(method_id)
        base = f"cn=initiatedBy,cn=system,{base}"
        initiators = await self._hierarchy.search({
            "base": base,
            "filter": {"cn": "*"},
            "attributes": ["cn"]
        })
        
        if not initiators:
            self._logger.warning(f"{self._config.svc_name} :: Метод '{method_id}' не имеет инициаторов.")
            return
        
        method_parent_tag = await self._hierarchy.get_parent(method_id)
        
        for initiator in initiators:
            
            # обновляем кэш ---------------------------------------------------------------------------
            initiator_cache = await self._cache.get(f"{initiator[0]}.{self._config.svc_name}").exec()
            if initiator_cache[0] is None:
                await self._cache.set(
                    name=f"{initiator[0]}.{self._config.svc_name}", 
                    obj=[{
                        "methodId": method_id,
                        "tagId": method_parent_tag
                    }]
                ).exec()
            else:
                await self._cache.append(
                    name=f"{initiator[0]}.{self._config.svc_name}", 
                    obj={
                        "methodId": method_id,
                        "tagId": method_parent_tag
                    }
                ).exec()
            # -----------------------------------------------------------------------------------------

            init_class = await self._hierarchy.get_node_class(initiator[0])
            match init_class:
                case "prsTag": 
                    await self._amqp_consume_queue.bind(
                        exchange=self._exchange,
                        routing_key=f"prsTag.app.data_set.{initiator[0]}"
                    )
                case "prsSchedule":
                    await self._amqp_consume_queue.bind(
                        exchange=self._exchange,
                        routing_key=f"prsSchedule.app.fire_event.{initiator[0]}"
                    )
                case _:
                    self._logger.error(f"{self._config.svc_name} :: Неверный класс '{init_class}' инициатора '{initiator[0]}' для метода '{method_id}'")
                    continue

    async def _unbind_method(self, method_id: str):
        pass

    async def _make_method_cache(self, method_id: str):
        """
        1) <initiator_id>.methods_app = 
            {
                "<method_id>": "<tag_id>"
            }
        2) <method_id>.methods_app = [
                "<initiator_id1>", "<initiator_id2>"
            ]
        """
        await self._delete_method_cache(method_id)

        payload = {
            "id": method_id,
            "attributes": ["prsActive"]
        }
        method_data = await self._hierarchy.search(payload=payload)
        if not method_data:
            self._logger.error(f"{self._config.svc_name} :: Нет данных по методу {method_id}.")
            return None
        method = method_data[0]
        if method[2]["prsActive"][0] =='FALSE':
            self._logger.warning(f"{self._config.svc_name} :: Метод '{method_id}' неактивен.")
            return False
        
        payload = {
            "base": f"cn=initiatedBy,cn=system,{method[1]}",
            "scope": CN_SCOPE_ONELEVEL,
            "filter": {"cn": ["*"]},
            "attributes": ["cn"]
        }
        initiators = await self._hierarchy.search(payload=payload)
        if not initiators:
            self._logger.warning(f"{self._config.svc_name} :: Метод '{method_id}' не имеет инициаторов.")
            return False
        
        parent_tag = await self._hierarchy.get_parent(method_id)

        for initiator in initiators:
            initiator_cache = await self._cache.get(f"{initiator[0]}.{self._config.svc_name}").exec()
            if initiator_cache[0] is None:
                await self._cache.set(
                    name=f"{initiator[0]}.{self._config.svc_name}",
                    obj={
                        method_id: parent_tag
                    }
                ).exec()
            else:
                await self._cache.set(
                    name=f"{initiator[0]}.{self._config.svc_name}",
                    key=method_id,
                    obj=parent_tag
                ).exec()
        return True

    async def _get_methods(self) -> None:
        # пока работаем только с вычислительными методами для тегов!
        # prsEntityTypeCode = 0
        get_methods = {
            "filter": {
                "objectClass": ["prsMethod"],
                "prsActive": [True],
                "prsEntityTypeCode": [0]
            },
            "attributes": ["cn"]
        }
        methods = await self._hierarchy.search(get_methods)

        for method in methods:
            await self._make_method_cache(method[0])
            await self._bind_method(method[0])

    async def on_startup(self) -> None:
        await super().on_startup()
        try:
            await self._get_methods()
        except Exception as ex:
            self._logger.error(f"{self._config.svc_name} :: Ошибка чтения методов: {ex}")

    async def _amqp_connect(self) -> None:
        await super()._amqp_connect()

        self._rpc_executor = NullExecutor(Registry(project=self._config.svc_name))
        await self._rpc_executor.setup()
        self._rpc_exchange = RabbitMQBroker(
            self._rpc_executor, amqp_url=self._config.broker["amqp_url"]
        )
        await self._rpc_exchange.setup()
        self._logger.debug(f"Methods broker: {self._method_broker}")

settings = MethodsAppSettings()

app = MethodsApp(settings=settings, title="`MethodsApp` service")
