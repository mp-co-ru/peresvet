"""
Модуль содержит классы, описывающие входные данные для команд CRUD для тегов
и класс сервиса ``methods_api_crud_svc``.
"""
import sys
import json
from uuid import uuid4

from patio import NullExecutor, Registry
from patio_rabbitmq import RabbitMQBroker

sys.path.append(".")

import src.common.times as times

from src.common.app_svc import AppSvc
from src.common.hierarchy import CN_SCOPE_ONELEVEL, CN_SCOPE_SUBTREE
from src.common.amqp_rpc import NO_AMQP_RPC_REPLY
from src.services.methods.app.methods_app_settings import MethodsAppSettings
from src.services.methods.app.method_param_resolve import parse_parameter_config, resolve_parameter_value

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
        self._handlers["prsMethod.app.virtual_data_get"] = self._virtual_data_get

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

    async def _method_entity_type(self, method_id: str) -> int:
        res = await self._hierarchy.search(
            {"id": method_id, "attributes": ["prsEntityTypeCode"]}
        )
        if not res:
            return 0
        raw = res[0][2].get("prsEntityTypeCode", ["0"])
        if isinstance(raw, list):
            raw = raw[0] if raw else 0
        try:
            return int(raw)
        except Exception:
            return 0

    async def _created(self, mes: dict, routing_key: str = None):
        await self._make_method_cache(mes["id"])
        if await self._method_entity_type(mes["id"]) != 1:
            await self._bind_method(mes["id"])

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
            if await self._method_entity_type(mes['id']) != 1:
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

        async with self._cache.get_redis() as r:
            methods_ids = await r.json().get(f"{initiator}.{self._config.svc_name}")
        if not methods_ids:
            self._logger.error(f"{self._config.svc_name} :: К расписанию '{initiator}' не привязаны методы.")
            return

        self._logger.debug(f"{self._config.svc_name} :: methods_ids: {methods_ids}")
        for method_id, tag_id in methods_ids.items():
            if await self._method_entity_type(method_id) == 1:
                continue
            parameters = await self._hierarchy.search({
                "base": method_id,
                "filter": {"cn": ["*"], "objectClass": ["prsMethodParameter"]},
                "attributes": ["prsJsonConfigString", "prsIndex", "cn"]
            })
            await self._calc_tag(tag_id, method_id, parameters, [mes['time'], None, None])

    async def _tag_has_datastorage_tagdata(self, tag_id: str) -> bool:
        """Тег привязан к хранилищу в модели — ответ на data_set даст dataStorages."""
        try:
            ds_root = await self._hierarchy.get_node_id("cn=dataStorages,cn=prs")
        except Exception:
            return False
        res = await self._hierarchy.search(
            {
                "base": ds_root,
                "scope": CN_SCOPE_SUBTREE,
                "filter": {"cn": [tag_id], "objectClass": ["prsDatastorageTagData"]},
                "attributes": ["cn"],
                "deref": False,
            }
        )
        return bool(res)

    async def _start_method_by_tag(self, mes: dict, routing_key: str = None) -> dict:

        self._logger.debug(f"Run methods. Data: {mes}")

        tag_ids: list[str] = []
        async with self._cache.get_redis() as r:
            for tag_item in mes["data"]:
                tag_id = tag_item["tagId"]
                tag_ids.append(tag_id)
                tag_data = tag_item["data"]
                methods = await r.json().get(f"{tag_id}.{self._config.svc_name}")
                if not methods:
                    self._logger.error(f"{self._config.svc_name} :: К тегу '{tag_id}' не привязаны методы.")
                    continue

                self._logger.debug(f"methods_ids: {methods}")
                for method_id, tag_id in methods.items():
                    if await self._method_entity_type(method_id) == 1:
                        continue
                    parameters = await self._hierarchy.search({
                        "base": method_id,
                        "filter": {"cn": ["*"], "objectClass": ["prsMethodParameter"]},
                        "attributes": ["prsJsonConfigString", "prsIndex", "cn"]
                    })
                    for tag_data_item in tag_data:
                        await self._calc_tag(tag_id, method_id, parameters, tag_data_item)

        if not tag_ids:
            return {}
        for tid in tag_ids:
            if not await self._tag_has_datastorage_tagdata(tid):
                return {}
        return NO_AMQP_RPC_REPLY

    async def _calc_tag(self, tag_id: str, method_id: str, parameters: dict, data: list[int | None]) -> None:

        self._logger.debug(f"calc_tag. tag_id: {tag_id}; method_id: {method_id}; parameters: {parameters}; data: {data}")

        parameters_data = []
        for parameter in parameters:
            cfg = parse_parameter_config(parameter[2]["prsJsonConfigString"][0])
            self._logger.debug(f"param cfg: {cfg}")
            param_data = await resolve_parameter_value(
                cfg,
                post_message=self._post_message,
                client_request=None,
                initiator_finish=data[0],
                initiator_point=data,
                virtual_resolution_tag_id=tag_id,
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

        parameters_data.sort(key=lambda item: (item["index"], 1000)[item["index"] is None])
        params_data = [item["data"] for item in parameters_data]

        method_name = await self._hierarchy.search(
            {
                "id": method_id,
                "attributes": ["prsMethodAddress"]
            }
        )

        self._logger.debug(f"Before call: method_id: {method_id}; method_name: {method_name}")

        method_addr = method_name[0][2]["prsMethodAddress"][0]
        if isinstance(method_addr, str):
            method_addr = method_addr.strip()
        rpc_call_id = str(uuid4())[:8]
        self._logger.debug(
            f"{self._config.svc_name} :: [methods_rpc] call_id={rpc_call_id} "
            f"source=data_set_calc_tag method_addr={method_addr!r} method_id={method_id} "
            f"output_tag_id={tag_id} param_slots={len(params_data)}"
        )
        try:
            res = await self._rpc_exchange.call(method_addr, *params_data)
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
                        (data[0], res, None)
                    ]
                }
            ]
        }, reply=False, routing_key=f"prsTag.app_api_client.data_set.{tag_id}")

    async def _virtual_data_get(self, mes: dict, routing_key: str | None = None) -> dict:
        method_id = mes.get("methodId")
        tag_id = mes.get("tagId")
        client_request = mes.get("clientRequest")
        if not method_id or not tag_id:
            return {"error": {"code": 422, "message": "В сообщении нужны methodId и tagId."}}
        parent, _ = await self._hierarchy.get_parent(method_id)
        if parent != tag_id:
            return {"error": {"code": 400, "message": "Метод не принадлежит указанному тегу."}}
        if await self._method_entity_type(method_id) != 1:
            return {"error": {"code": 400, "message": "Метод не помечен как виртуальный (prsEntityTypeCode != 1)."}}
        parameters = await self._hierarchy.search({
            "base": method_id,
            "filter": {"cn": ["*"], "objectClass": ["prsMethodParameter"]},
            "attributes": ["prsJsonConfigString", "prsIndex", "cn"]
        })
        finish_ts = times.now_int()
        if isinstance(client_request, dict):
            fv = client_request.get("finish")
            if fv is not None:
                try:
                    finish_ts = int(fv) if isinstance(fv, int) else int(times.ts(fv))
                except Exception:
                    finish_ts = times.now_int()

        parameters_data: list[dict] = []
        for parameter in parameters:
            cfg = parse_parameter_config(parameter[2]["prsJsonConfigString"][0])
            param_data = await resolve_parameter_value(
                cfg,
                post_message=self._post_message,
                client_request=client_request if isinstance(client_request, dict) else None,
                initiator_finish=finish_ts,
                initiator_point=None,
                virtual_resolution_tag_id=tag_id,
            )
            if parameter[2]["prsIndex"][0] is None:
                index = None
            else:
                index = int(parameter[2]["prsIndex"][0])
            parameters_data.append({"index": index, "data": param_data})

        parameters_data.sort(key=lambda item: (item["index"], 1000)[item["index"] is None])
        params_data = [item["data"] for item in parameters_data]

        method_name = await self._hierarchy.search(
            {"id": method_id, "attributes": ["prsMethodAddress"]}
        )
        if not method_name:
            return {"error": {"code": 404, "message": "Метод не найден."}}
        method_addr = method_name[0][2]["prsMethodAddress"][0]
        if isinstance(method_addr, str):
            method_addr = method_addr.strip()
        rpc_call_id = str(uuid4())[:8]
        self._logger.debug(
            f"{self._config.svc_name} :: [methods_rpc] call_id={rpc_call_id} "
            f"source=virtual_data_get method_addr={method_addr!r} method_id={method_id} "
            f"virtual_tag_id={tag_id} param_slots={len(params_data)}"
        )
        try:
            res = await self._rpc_exchange.call(method_addr, *params_data)
        except Exception as ex:
            self._logger.error(f"{self._config.svc_name} :: Виртуальный метод {method_id}: {ex}")
            return {"error": {"code": 500, "message": str(ex)}}
        if isinstance(res, dict) and res.get("error") is not None:
            return {"error": {"code": 500, "message": str(res.get("error"))}}

        return {
            "data": [
                {
                    "tagId": tag_id,
                    "data": [
                        (finish_ts, res, None),
                    ],
                }
            ]
        }

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
        async with self._cache.get_redis() as r:
            method_cache = await r.json().get(f"{method_id}.{self._config.svc_name}")
            if method_cache is None:
                return

            async with r.pipeline() as p:
                for initiator_id in method_cache:
                    res = await (p.json().delete(
                        key=f"{initiator_id}.{self._config.svc_name}",
                        path=method_id
                    ).json().get(f"{initiator_id}.{self._config.svc_name}")).execute()

                    if res is not None:
                        if not res[1].keys():
                            await r.json().delete(
                                key=f"{initiator_id}.{self._config.svc_name}"
                            )

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
        await self._bind_method(method_id, False)

        if await self._method_entity_type(method_id) == 1:
            self._logger.debug(
                f"{self._config.svc_name} :: Метод '{method_id}' (prsEntityTypeCode=1): "
                "кэш инициаторов не строится."
            )
            return True

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
        async with self._cache.get_redis() as r:
            for initiator in initiators:
                initiator_id = initiator[2]["cn"][0]
                initiators_ids.append(initiator_id)
                initiator_cache = await r.json().get(f"{initiator_id}.{self._config.svc_name}")
                if initiator_cache is None:
                    await r.json().set(
                        name=f"{initiator_id}.{self._config.svc_name}",
                        path="$",
                        obj={
                            method_id: parent_tag
                        }
                    )
                else:
                    await r.json().set(
                        name=f"{initiator_id}.{self._config.svc_name}",
                        path=method_id,
                        obj=parent_tag
                    )

            await r.json().set(
                name=f"{method_id}.{self._config.svc_name}", path="$", obj=initiators_ids
            )

        return True

    async def _get_methods(self):
        payload = {
            "filter": {"objectClass": ["prsMethod"], "prsActive": ["TRUE"]},
            "attributes": ["cn"]
        }
        methods = await self._hierarchy.search(payload=payload)
        for method in methods:
            ok = await self._make_method_cache(method[0])
            if ok and await self._method_entity_type(method[0]) != 1:
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
