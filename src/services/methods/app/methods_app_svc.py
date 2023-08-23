"""
Модуль содержит классы, описывающие входные данные для команд CRUD для тегов
и класс сервиса ``methods_api_crud_svc``.
"""
import sys
import json
from ldap.dn import str2dn, dn2str
from patio import NullExecutor, Registry
from patio_rabbitmq import RabbitMQBroker

sys.path.append(".")

from src.common import svc
from src.common.hierarchy import CN_SCOPE_BASE, CN_SCOPE_ONELEVEL, CN_SCOPE_SUBTREE
from src.common.cache import Cache
from src.services.methods.app.methods_app_settings import MethodsAppSettings

class MethodsApp(svc.Svc):
    """Сервис работы с методами.

    Формат ожидаемых сообщений

    """

    _outgoing_commands = {}

    def __init__(self, settings: MethodsAppSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)
        self._cache = Cache(settings.ldap_url)
        self._method_broker = None

    def _set_incoming_commands(self) -> dict:
        return {
            "tags.uploadData": self._tag_changed
        }

    def _cache_key(self, *args):
        return f"{'.'.join(args)}"

    async def _tag_changed(self, mes: dict) -> dict:

        self._logger.debug(f"Run methods. Data: {mes}")

        """
        {
            "action": "tags.uploadData",
            "data": {
                "data": [
                    tag_item
                ]
            }
        }
        """

        for tag_item in mes["data"]["data"]:
            tag_id = tag_item["tagId"]
            tag_data = tag_item["data"]
            methods_ids = await self._cache.get_key(
                self._cache_key(tag_id, self._config.svc_name), json_loads=True
            )
            if not methods_ids:
                self._logger.debug(f"К тегу {tag_id} не привязаны методы.")
                continue

            """
            methods_ids = [
                {
                    "methodId": "...",
                    "tagId": "..."
                }
            ]
            """
            self._logger.debug(f"methods_ids: {methods_ids}")
            for item in methods_ids:
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
            mes = {"action": "client.getData", "data": request}

            self._logger.debug(f"mes: {mes}")

            param_data = await self._post_message(
                mes=mes,
                reply=True,
                routing_key="tags_app_api_consume"
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
            async with NullExecutor(Registry(project=self._config.svc_name)) as executor:
                async with RabbitMQBroker(
                    executor, amqp_url=self._config.amqp_url,
                ) as broker:
                    res = await broker.call(method_name[0][2]["prsMethodAddress"][0], *params_data)

                    self._logger.debug(f"Результат: {res}. Тег: {tag_id}")
        except Exception as ex:
            self._logger.error(f"Ошибка вычисления тега {tag_id}: {ex}")
            return

        await self._post_message(mes={
            "action": "tags.setData",
            "data": {
                "data": [
                    {
                        "tagId": tag_id,
                        "data": [
                            (res, data[1], None)
                        ]
                    }
                ]
            }
        }, reply=False, routing_key="tags_app_consume")

    async def _read_methods(self) -> None:
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

        cache_data = {}
        for method in methods:
            base_node = await self._hierarchy.get_node_id(
                f"cn=initiatedBy,cn=system,{method[1]}"
            )
            initiatedBy_nodes = await self._hierarchy.search(
                {
                    "base": base_node,
                    "scope": CN_SCOPE_ONELEVEL,
                    "filter": {
                        "cn": ['*']
                    },
                    "attributes": ["cn"]
                })

            parent_tag_id = await self._hierarchy.get_parent(method[0])
            for initiatedBy_id in initiatedBy_nodes:
                tag_initiator = initiatedBy_id[2]["cn"][0]
                await self._amqp_consume["queue"].bind(
                    exchange=self._amqp_consume["exchanges"]["main"]["exchange"],
                    routing_key=tag_initiator
                )
                cache_data.setdefault(tag_initiator, [])
                cache_data[tag_initiator].append({
                    "methodId": method[0],
                    "tagId": parent_tag_id[0]
                })

            self._logger.debug(f"Метод {method[0]} прочитан.")

        for tag_id, methods_ids in cache_data.items():
            await self._cache.set_key(
                self._cache_key(tag_id, self._config.svc_name),
                methods_ids
            )

    async def on_startup(self) -> None:
        await super().on_startup()
        await self._cache.connect()
        try:
            await self._read_methods()
        except Exception as ex:
            self._logger.error(f"Ошибка чтения методов: {ex}")

    async def _amqp_connect(self) -> None:
        await super()._amqp_connect()

        """
        executor = NullExecutor(Registry(project=self._config.svc_name))
        self._method_broker = RabbitMQBroker(
            executor, amqp_url="amqp://prs:Peresvet21@localhost/"
        )
        self._logger.debug(f"Methods broker: {self._method_broker}")
        """

settings = MethodsAppSettings()

app = MethodsApp(settings=settings, title="`MethodsApp` service")
