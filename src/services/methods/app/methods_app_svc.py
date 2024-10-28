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
    Логика работы сервиса.
    Старт:
    1) Класс-предок подписывается за нас на события изменения экземпляров
       сущности.
    2) Создаём для каждого активного(!) метода кэш. 
       Ключ: "<method_id>.<svc_name>".
       Значение: {
            "initiators": ["initiator_id1", "initiator_id2", ...]
       }
    3) При построении кэшей методов строим кэш для каждого инициатора:
       Ключ: "<initiator_id>.<svc_name>".
       Значение: {
            "<method_id>": "<calculated_tag_id>",
            ...
       }
    4) Подписываемся также на события удаления инициаторов!

    ** Сервис "prsMethod.model" подписывается на события удаления инициаторов! После удаления
    инициатора он посылает сообщение updated, при обработке которого этот сервис перестраивает
    кэш метода.


    Работа:
    1) created:
       Если метод активный, создаём кэш по вышеописанному сценарию.
    2) Updated:
       Если метод становится неактивным, удаляем его кэш.
       Если активный, кэш перестраиваем.
       То есть если в процессе обновления тега изменился список инициаторов - 
       мы всё равно перестраиваем кэш.
    3) Deleted:
       Удаляем кэш метода.
    4) При создании кэша метода подписываемся на события инициаторов (изменение значений тега и 
       генерация событий расписания)
    5) При удалении кэша метода удаляем также и соответствующий ключ из
       кэша инициатора и смотрим: если кэш инициатора остался пустой, то 
       удаляем кэш инициатора и отписываемся от генерируемых событий.


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
        self._handlers["prsTag.app.data_set.*"] = self._start_method_by_tag
        self._handlers["prsSchedule.app.fire_event.*"] = self._start_method_by_sched

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

    async def _updated(self, mes: dict, routing_key: str = None):
        """
        Нас интересует только смена флага active
        """
        payload = {
            "id": mes['id'],
            "attributes": ["prsActive"]
        }
        method_data = await self._hierarchy.search(payload=payload)
        active = method_data[0][2]["prsActive"][0] == 'TRUE'
        if active:
            await self._make_method_cache(mes['id'])
            await self._bind_method(mes['id'], True)
        else:
            await self._delete_method_cache(mes['id'])
            await self._bind_method(mes['id'], False)

    
    async def _start_method_by_sched(self, mes: dict, routing_key: str = None) -> dict:
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
            self._logger.error(f"{self._config.svc_name} :: К расписанию '{initiator}' не привязаны методы.")
            return

        """
        methods_ids = {
            "methodId": "tagId",
            ...
        }
        """
        self._logger.debug(f"{self._config.svc_name} :: methods_ids: {methods_ids[0]}")
        for method_id, tag_id in methods_ids[0].items():
            parameters = await self._hierarchy.search({
                "base": method_id,
                "filter": {"cn": ["*"], "objectClass": ["prsMethodParameter"]},
                "attributes": ["prsJsonConfigString", "prsIndex", "cn"]
            })
            await self._calc_tag(tag_id, method_id, parameters, [None, mes['time'], None])

    async def _start_method_by_tag(self, mes: dict, routing_key: str = None) -> dict:

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
            methods = await self._cache.get(f"{tag_id}.{self._config.svc_name}").exec()
            if not methods[0]:
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
            self._logger.debug(f"methods_ids: {methods[0]}")
            for method_id, tag_id in methods[0].items():
                parameters = await self._hierarchy.search({
                    "base": method_id,
                    "filter": {"cn": ["*"], "objectClass": ["prsMethodParameter"]},
                    "attributes": ["prsJsonConfigString", "prsIndex", "cn"]
                })
                for tag_data_item in tag_data:
                    await self._calc_tag(tag_id, method_id, parameters, tag_data_item)

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

    async def _deleting(self, mes: dict, routing_key: str = None):
        # перед удалением тревоги
        await self._bind_method(mes['id'], False)
        await self._delete_method_cache(mes['id'])
        
    async def _bind_method(self, method_id: str, bind: bool = True):
        # только логика привязки
        # проверка активности метода производится вызывающим методом
        # привязка к сообщениям prsMethod.model.* выполняется при старте сервиса и здесь не меняется
        base = await self._hierarchy.get_node_dn(method_id)
        base = f"cn=initiatedBy,cn=system,{base}"
        initiators = await self._hierarchy.search({
            "base": base,
            "scope": CN_SCOPE_ONELEVEL,
            "filter": {"cn": "*"},
            "attributes": ["cn"]
        })
        
        if not initiators:
            self._logger.warning(f"{self._config.svc_name} :: Метод '{method_id}' не имеет инициаторов.")
            return
        
        for initiator in initiators:            
            initiator_id = initiator[2]["cn"][0]
            init_class = await self._hierarchy.get_node_class(initiator_id)
            match init_class:
                case "prsTag": 
                    if bind:
                        await self._amqp_consume_queue.bind(
                            exchange=self._exchange,
                            routing_key=f"{init_class}.app.data_set.{initiator_id}"
                        )
                    else:
                        await self._amqp_consume_queue.unbind(
                            exchange=self._exchange,
                            routing_key=f"{init_class}.app.data_set.{initiator_id}"
                        )
                case "prsSchedule":
                    if bind: 
                        await self._amqp_consume_queue.bind(
                            exchange=self._exchange,
                            routing_key=f"prsSchedule.app.fire_event.{initiator_id}"
                        )
                    else:
                        await self._amqp_consume_queue.unbind(
                            exchange=self._exchange,
                            routing_key=f"prsSchedule.app.fire_event.{initiator_id}"
                        )
                case _:
                    self._logger.error(f"{self._config.svc_name} :: Неверный класс '{init_class}' инициатора '{initiator_id}' для метода '{method_id}'")
                    continue

    async def _delete_method_cache(self, method_id: str):
        method_cache = await self._cache.get(f"{method_id}.{self._config.svc_name}").exec()
        if method_cache[0] is None:
            return
        for initiator_id in method_cache[0]:
            res = await self._cache.delete(
                name=f"{initiator_id}.{self._config.svc_name}",
                key=method_id
            ).get(name=f"{initiator_id}.{self._config.svc_name}").exec()
            if not res[1].keys():
                await self._cache.delete(
                    name=f"{initiator_id}.{self._config.svc_name}"
                ).exec()

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

        method_dn = await self._hierarchy.get_node_dn(method_id)
        payload = {
            "base": f"cn=initiatedBy,cn=system,{method_dn}",
            "scope": CN_SCOPE_ONELEVEL,
            "filter": {"cn": ["*"]},
            "attributes": ["cn"]
        }
        initiators = await self._hierarchy.search(payload=payload)
        if not initiators:
            self._logger.warning(f"{self._config.svc_name} :: Метод '{method_id}' не имеет инициаторов.")
            return False
        
        parent_tag, _ = await self._hierarchy.get_parent(method_id)

        initiators_ids = []
        for initiator in initiators:
            initiator_id = initiator[2]["cn"][0]
            initiators_ids.append(initiator_id)
            initiator_cache = await self._cache.get(f"{initiator_id}.{self._config.svc_name}").exec()
            if initiator_cache[0] is None:
                await self._cache.set(
                    name=f"{initiator_id}.{self._config.svc_name}",
                    obj={
                        method_id: parent_tag
                    }
                ).exec()
            else:
                await self._cache.set(
                    name=f"{initiator_id}.{self._config.svc_name}",
                    key=method_id,
                    obj=parent_tag
                ).exec()

        await self._cache.set(
            name=f"{method_id}.{self._config.svc_name}",
            obj=initiators_ids
        ).exec()

        return True

    async def _get_methods(self):
        payload = {
            "filter": {"objectClass": ["prsMethod"], "prsActive": ["TRUE"]},
            "attributes": ["cn"]
        }
        methods = await self._hierarchy.search(payload=payload)
        for method in methods:
            await self._make_method_cache(method[0])
            await self._bind_method(method[0])

    async def on_startup(self) -> None:
        
        await super().on_startup()
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsTag.app.data_set.*")
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsSchedule.app.fire_event.*")
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
