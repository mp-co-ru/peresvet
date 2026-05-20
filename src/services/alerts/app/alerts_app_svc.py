"""
Сервис тревог: пороговые, с накоплением по времени в диапазоне и на основе метода (prsMethod).
Состояние в Redis общее для всех экземпляров сервиса; очередь AMQP с фиксированным именем
даёт конкурирующее потребление — одно сообщение обрабатывает один воркер.
"""
import sys
import json
from uuid import uuid4

from patio import NullExecutor, Registry
from patio_rabbitmq import RabbitMQBroker

sys.path.append(".")

from src.common.app_svc import AppSvc
from src.common.amqp_rpc import NO_AMQP_RPC_REPLY
from src.services.alerts.app.alerts_app_settings import AlertsAppSettings
from src.common.hierarchy import CN_SCOPE_ONELEVEL, CN_SCOPE_SUBTREE
from src.services.methods.app.method_param_resolve import (
    parse_parameter_config,
    resolve_parameter_value,
)


def _alert_kind(cfg: dict) -> str:
    k = (cfg.get("kind") or "simple").strip().lower()
    if k in ("simple", "duration", "complex"):
        return k
    return "simple"


def _truthy_method_result(res) -> bool:
    if isinstance(res, bool):
        return res
    if isinstance(res, (int, float)):
        return bool(res)
    if isinstance(res, str):
        return res.strip().lower() in ("true", "1", "yes", "on")
    if isinstance(res, dict) and res.get("error") is not None:
        return False
    return False


class AlertsApp(AppSvc):
    """Сервис работы с тревогами."""

    #: суффикс ключа Redis: ``<initiator_id>.<svc_name><_ic>`` → {``<alert_id>``: ``<method_id>``}
    _INITIATOR_COMPLEX_SUFFIX = "_ic"

    def __init__(self, settings: AlertsAppSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)
        self._rpc_executor = None
        self._rpc_exchange = None

    def _add_app_handlers(self):
        self._handlers[f"{self._config.hierarchy['class']}.app_api.get_alarms"] = self._get_alarms
        self._handlers[f"{self._config.hierarchy['class']}.app_api.ack_alarm"] = self._ack_alarm
        self._handlers["prsTag.app.data_set.*"] = self._tag_value_changed
        self._handlers["prsSchedule.app.fire_event.*"] = self._schedule_fire_for_complex_alerts

    def _initiator_complex_key(self, initiator_id: str) -> str:
        return f"{initiator_id}.{self._config.svc_name}{self._INITIATOR_COMPLEX_SUFFIX}"

    def _alert_cache_key(self, alert_id: str) -> str:
        return f"{alert_id}.{self._config.svc_name}"

    async def _amqp_connect(self) -> None:
        await super()._amqp_connect()
        self._rpc_executor = NullExecutor(Registry(project=self._config.svc_name))
        await self._rpc_executor.setup()
        self._rpc_exchange = RabbitMQBroker(
            self._rpc_executor, amqp_url=self._config.broker["amqp_url"]
        )
        await self._rpc_exchange.setup()

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

    async def _deleting(self, mes: dict, routing_key: str = None):
        old_key = self._alert_cache_key(mes["id"])
        async with self._cache.get_redis() as r:
            old_cached = await r.json().get(old_key)
        if old_cached:
            await self._clear_complex_initiator_state(old_cached)
        await self._delete_alert_cache(mes["id"])
        await self._unbind_alert(mes["id"])

    async def _bind_alert(self, alert_id: str):
        async with self._cache.get_redis() as r:
            cached = await r.json().get(self._alert_cache_key(alert_id))
        if not cached:
            return
        kind = cached.get("kind", "simple")
        if kind in ("simple", "duration"):
            tag_id, _ = await self._hierarchy.get_parent(alert_id)
            await self._amqp_consume_queue.bind(
                self._exchange, f"prsTag.app.data_set.{tag_id}"
            )
        if kind == "complex":
            for it in cached.get("complexInitiators") or []:
                iid, icls = it["id"], it["class"]
                if icls == "prsTag":
                    await self._amqp_consume_queue.bind(
                        self._exchange, f"prsTag.app.data_set.{iid}"
                    )
                elif icls == "prsSchedule":
                    await self._amqp_consume_queue.bind(
                        self._exchange, f"prsSchedule.app.fire_event.{iid}"
                    )

    async def _unbind_alert(self, alert_id: str):
        tag_id, _ = await self._hierarchy.get_parent(alert_id)
        payload = {
            "base": tag_id,
            "scope": CN_SCOPE_ONELEVEL,
            "filter": {"objectClass": ["prsAlert"], "prsActive": ["TRUE"]},
            "attributes": ["prsJsonConfigString"],
        }
        res = await self._hierarchy.search(payload)

        need_parent_bind = False
        for alert in res:
            if alert[0] == alert_id:
                continue
            try:
                cfg = json.loads(alert[2]["prsJsonConfigString"][0])
            except Exception:
                cfg = {}
            if _alert_kind(cfg) != "complex":
                need_parent_bind = True
                break

        if not need_parent_bind:
            try:
                await self._amqp_consume_queue.unbind(
                    self._exchange, f"prsTag.app.data_set.{tag_id}"
                )
            except Exception:
                pass
            self._logger.info(
                f"{self._config.svc_name} :: Отвязка от изменений тега {tag_id}"
            )

    async def _any_simple_duration_alert_on_tag(self, tag_id: str) -> bool:
        payload = {
            "base": tag_id,
            "scope": CN_SCOPE_ONELEVEL,
            "filter": {"objectClass": ["prsAlert"], "prsActive": ["TRUE"]},
            "attributes": ["prsJsonConfigString"],
        }
        rows = await self._hierarchy.search(payload)
        for row in rows:
            try:
                cfg = json.loads(row[2]["prsJsonConfigString"][0])
            except Exception:
                cfg = {}
            if _alert_kind(cfg) != "complex":
                return True
        return False

    async def _maybe_unbind_parent_tag_data_set(self, tag_id: str) -> None:
        if await self._any_simple_duration_alert_on_tag(tag_id):
            return
        try:
            await self._amqp_consume_queue.unbind(
                self._exchange, f"prsTag.app.data_set.{tag_id}"
            )
        except Exception:
            pass
        self._logger.info(
            f"{self._config.svc_name} :: Отвязка от тега {tag_id} "
            "(нет простых/задержечных тревог)."
        )

    async def _clear_complex_initiator_state(self, cached: dict) -> None:
        if cached.get("kind") != "complex":
            return
        aid = cached["alertId"]
        async with self._cache.get_redis() as r:
            for it in cached.get("complexInitiators") or []:
                iid = it["id"]
                icls = it["class"]
                key = self._initiator_complex_key(iid)
                await r.json().delete(key, path=aid)
                remaining = await r.json().get(key)
                if remaining in (None, {}):
                    try:
                        await r.delete(key)
                    except Exception:
                        pass
                    if icls == "prsTag":
                        try:
                            await self._amqp_consume_queue.unbind(
                                self._exchange, f"prsTag.app.data_set.{iid}"
                            )
                        except Exception:
                            pass
                    elif icls == "prsSchedule":
                        try:
                            await self._amqp_consume_queue.unbind(
                                self._exchange, f"prsSchedule.app.fire_event.{iid}"
                            )
                        except Exception:
                            pass

    async def _created(self, mes: dict, routing_key: str = None):
        active = await self._make_alert_cache(mes["id"])
        if active:
            await self._bind_alert(mes["id"])
            tag_id, _ = await self._hierarchy.get_parent(mes["id"])
            await self._maybe_unbind_parent_tag_data_set(tag_id)

    async def _updated(self, mes: dict, routing_key: str = None):
        active = await self._make_alert_cache(mes["id"])
        if active:
            await self._bind_alert(mes["id"])
            tag_id, _ = await self._hierarchy.get_parent(mes["id"])
            await self._maybe_unbind_parent_tag_data_set(tag_id)
        else:
            await self._unbind_alert(mes["id"])

    async def _delete_alert_cache(self, alert_id: str):
        async with self._cache.get_redis() as r:
            await r.json().delete(self._alert_cache_key(alert_id))

    async def _make_alert_cache(self, alert_id: str) -> bool | None:
        old_key = self._alert_cache_key(alert_id)
        async with self._cache.get_redis() as r:
            old_cached = await r.json().get(old_key)
        if old_cached:
            await self._clear_complex_initiator_state(old_cached)

        await self._delete_alert_cache(alert_id=alert_id)

        payload = {
            "id": alert_id,
            "attributes": [
                "prsActive",
                "cn",
                "description",
                "prsJsonConfigString",
            ],
        }
        alert_row = await self._hierarchy.search(payload)
        if not alert_row:
            self._logger.error(
                f"{self._config.svc_name} :: Нет данных по тревоге {alert_id}."
            )
            return None

        alert = alert_row[0]
        tag_id, _ = await self._hierarchy.get_parent(alert_id)

        active = alert[2]["prsActive"][0] == "TRUE"
        if not active:
            self._logger.warning(
                f"{self._config.svc_name} :: Тревога '{alert_id}' неактивна."
            )
            return False

        try:
            alert_config = json.loads(alert[2]["prsJsonConfigString"][0])
        except (json.JSONDecodeError, TypeError):
            alert_config = None

        if not isinstance(alert_config, dict):
            self._logger.error(
                f"{self._config.svc_name} :: У тревоги '{alert_id}' неверная конфигурация."
            )
            return None

        kind = _alert_kind(alert_config)
        if alert_config.get("autoAck") is None:
            self._logger.error(
                f"{self._config.svc_name} :: У тревоги '{alert_id}' не задан autoAck."
            )
            return None

        if kind == "simple":
            if (
                alert_config.get("value") is None
                or alert_config.get("high") is None
            ):
                self._logger.error(
                    f"{self._config.svc_name} :: У простой тревоги '{alert_id}' "
                    "нужны value и high."
                )
                return None
        elif kind == "duration":
            for fld in ("rangeLow", "rangeHigh", "durationMicroseconds"):
                if alert_config.get(fld) is None:
                    self._logger.error(
                        f"{self._config.svc_name} :: У тревоги с задержкой '{alert_id}' "
                        f"нужно поле {fld}."
                    )
                    return None
        elif kind == "complex":
            method_id = (alert_config.get("methodId") or "").strip()
            if not method_id:
                self._logger.error(
                    f"{self._config.svc_name} :: У сложной тревоги '{alert_id}' "
                    "нужен methodId."
                )
                return None
            parent_mid, _ = await self._hierarchy.get_parent(method_id)
            if parent_mid != alert_id:
                self._logger.error(
                    f"{self._config.svc_name} :: Метод {method_id} не является дочерним "
                    f"для тревоги {alert_id}."
                )
                return None
            if await self._method_entity_type(method_id) == 1:
                self._logger.error(
                    f"{self._config.svc_name} :: Для тревоги нельзя использовать "
                    f"виртуальный метод {method_id}."
                )
                return None

        alert_data: dict = {
            "alertId": alert_id,
            "tagId": tag_id,
            "kind": kind,
            "fired": False,
            "acked": False,
            "autoAck": alert_config["autoAck"],
            "cn": alert[2]["cn"][0],
            "description": alert[2]["description"][0],
        }

        if kind == "simple":
            alert_data["value"] = alert_config["value"]
            alert_data["high"] = alert_config["high"]
            alert_data["dwellStart"] = None
        elif kind == "duration":
            alert_data["rangeLow"] = float(alert_config["rangeLow"])
            alert_data["rangeHigh"] = float(alert_config["rangeHigh"])
            alert_data["durationMicroseconds"] = float(
                alert_config["durationMicroseconds"]
            )
            alert_data["dwellStart"] = None
        else:
            method_id = str(alert_config["methodId"]).strip()
            alert_data["methodId"] = method_id
            initiators = await self._load_method_initiators(method_id)
            if not initiators:
                self._logger.error(
                    f"{self._config.svc_name} :: У метода {method_id} нет инициаторов."
                )
                return None
            alert_data["complexInitiators"] = initiators
            async with self._cache.get_redis() as r:
                for it in initiators:
                    iid = it["id"]
                    key = self._initiator_complex_key(iid)
                    cur = await r.json().get(key)
                    if cur is None:
                        await r.json().set(name=key, path="$", obj={alert_id: method_id})
                    else:
                        await r.json().set(name=key, path=alert_id, obj=method_id)

        async with self._cache.get_redis() as r:
            await r.json().set(name=old_key, path="$", obj=alert_data)

        payload_activate = {"tagId": tag_id, "actual": True}
        res = await self._post_message(
            mes=payload_activate,
            reply=True,
            routing_key=f"prsTag.app_api_client.data_get.{tag_id}",
        )
        if res is not None:
            if res.get("data"):
                if kind in ("simple", "duration"):
                    await self._tag_value_changed(res, id_alert=alert_id)
            else:
                self._logger.warning(
                    f"{self._config.svc_name} :: Тег {tag_id} не имеет данных."
                )
            return True
        self._logger.warning(
            f"{self._config.svc_name} :: Тег {tag_id} не привязан к хранилищу."
        )
        return True

    async def _load_method_initiators(self, method_id: str) -> list[dict]:
        method_dn = await self._hierarchy.get_node_dn(method_id)
        payload = {
            "base": f"cn=initiatedBy,cn=system,{method_dn}",
            "scope": CN_SCOPE_ONELEVEL,
            "filter": {"cn": ["*"]},
            "attributes": ["cn"],
        }
        rows = await self._hierarchy.search(payload)
        out: list[dict] = []
        for row in rows:
            iid = row[2]["cn"][0]
            icls = await self._hierarchy.get_node_class(iid)
            if icls in ("prsTag", "prsSchedule"):
                out.append({"id": iid, "class": icls})
            else:
                self._logger.warning(
                    f"{self._config.svc_name} :: Инициатор {iid} класса {icls} "
                    f"для метода {method_id} пропущен."
                )
        return out

    async def _get_alarms(self, mes: dict, routing_key: str = None) -> dict:
        scope = (CN_SCOPE_ONELEVEL, CN_SCOPE_SUBTREE)[bool(mes.get("getChildren"))]

        get_alerts = {
            "base": mes.get("parentId"),
            "scope": scope,
            "filter": {"objectClass": ["prsAlert"], "prsActive": ["TRUE"]},
            "attributes": ["cn"],
        }

        alerts = await self._hierarchy.search(get_alerts)
        result: dict = {"data": []}
        async with self._cache.get_redis() as r:
            for alert in alerts:
                alarm = await r.json().get(self._alert_cache_key(alert[0]))
                if alarm is None:
                    self._logger.error(
                        f"{self._config.svc_name} :: Нет кэша для тревоги {alert[0]}"
                    )
                    continue

                if mes["fired"] and not alarm["fired"]:
                    continue

                res_item = {
                    "id": alert[0],
                    "cn": alarm["cn"],
                    "description": alarm["description"],
                    "start": (False, alarm["fired"])[bool(alarm["fired"])],
                    "finish": False,
                    "acked": (False, alarm["acked"])[bool(alarm["acked"])],
                }

                result["data"].append(res_item)

        return result

    async def _ack_alarm(self, mes: dict, routing_key: str = None):
        alert_id = mes["id"]
        alert_cache_key = self._alert_cache_key(alert_id)
        ack_ts = mes.get("x")
        async with self._cache.get_redis() as r:
            alert_data = await r.json().get(name=alert_cache_key)

            if not alert_data:
                self._logger.error(
                    f"{self._config.svc_name} :: Отсутствует кэш по тревоге {alert_id}."
                )
                return

            if not alert_data["fired"]:
                self._logger.warning(
                    f"{self._config.svc_name} :: Тревога {alert_id} неактивна."
                )
                return

            if alert_data["acked"]:
                self._logger.warning(
                    f"{self._config.svc_name} :: Тревога {alert_id} уже квитирована."
                )
                return

            alert_data["acked"] = ack_ts
            await r.json().set(name=alert_cache_key, path="$", obj=alert_data)

        await self._post_message(
            {"alertId": alert_id, "x": ack_ts},
            reply=False,
            routing_key=f"{self._config.hierarchy['class']}.app.alarm_acked.{alert_id}",
        )

    def _simple_condition_on(self, alert_data: dict, value) -> bool:
        threshold = alert_data["value"]
        if alert_data["high"]:
            try:
                return float(value) >= float(threshold)
            except (TypeError, ValueError):
                return False
        try:
            return float(value) < float(threshold)
        except (TypeError, ValueError):
            return False

    def _duration_band_on(self, alert_data: dict, value) -> bool:
        try:
            v = float(value)
            lo = float(alert_data["rangeLow"])
            hi = float(alert_data["rangeHigh"])
        except (TypeError, ValueError):
            return False
        return lo <= v <= hi

    async def _apply_simple_or_duration(
        self,
        r,
        alert_id: str,
        alert_data: dict,
        data_item: tuple,
    ) -> None:
        ts, value = data_item[0], data_item[1]
        kind = alert_data.get("kind", "simple")

        if alert_data["fired"]:
            if ts <= alert_data["fired"]:
                return
            if alert_data["acked"] and ts <= alert_data["acked"]:
                return

        if kind == "simple":
            alert_on = self._simple_condition_on(alert_data, value)
            alert_data["dwellStart"] = None
        else:
            in_band = self._duration_band_on(alert_data, value)
            if not in_band:
                alert_data["dwellStart"] = None
                alert_on = False
            elif alert_data["fired"]:
                alert_on = True
            else:
                if not alert_data.get("dwellStart"):
                    alert_data["dwellStart"] = ts
                need_us = int(float(alert_data["durationMicroseconds"]))
                alert_on = (ts - alert_data["dwellStart"]) >= need_us

        if (alert_data["fired"] and alert_on) or (
            not alert_data["fired"] and not alert_on
        ):
            return

        if not alert_data["fired"] and alert_on:
            await self._post_message(
                {"alertId": alert_id, "x": ts},
                reply=False,
                routing_key=f"{self._config.hierarchy['class']}.app.alarm_on.{alert_id}",
            )
            alert_data["fired"] = ts
            alert_data["dwellStart"] = None
            if alert_data["autoAck"]:
                await self._post_message(
                    {"alertId": alert_id, "x": ts},
                    reply=False,
                    routing_key=f"{self._config.hierarchy['class']}.app.alarm_acked.{alert_id}",
                )
                alert_data["acked"] = ts

        if alert_data["fired"] and not alert_on:
            await self._post_message(
                {"alertId": alert_id, "x": ts},
                reply=False,
                routing_key=f"{self._config.hierarchy['class']}.app.alarm_off.{alert_id}",
            )
            alert_data["fired"] = None
            alert_data["acked"] = None
            alert_data["dwellStart"] = None

    async def _eval_complex_method(
        self, alert_id: str, method_id: str, initiator_point: list
    ) -> bool:
        parameters = await self._hierarchy.search(
            {
                "base": method_id,
                "filter": {"cn": ["*"], "objectClass": ["prsMethodParameter"]},
                "attributes": ["prsJsonConfigString", "prsIndex", "cn"],
            }
        )
        parameters_data = []
        for parameter in parameters:
            cfg = parse_parameter_config(parameter[2]["prsJsonConfigString"][0])
            param_data = await resolve_parameter_value(
                cfg,
                post_message=self._post_message,
                client_request=None,
                initiator_finish=initiator_point[0],
                initiator_point=initiator_point,
                virtual_resolution_tag_id=alert_id,
            )
            if parameter[2]["prsIndex"][0] is None:
                index = None
            else:
                index = int(parameter[2]["prsIndex"][0])
            parameters_data.append({"index": index, "data": param_data})

        parameters_data.sort(
            key=lambda item: (item["index"], 1000)[item["index"] is None]
        )
        params_data = [item["data"] for item in parameters_data]

        method_name = await self._hierarchy.search(
            {"id": method_id, "attributes": ["prsMethodAddress"]}
        )
        if not method_name:
            return False
        method_addr = method_name[0][2]["prsMethodAddress"][0]
        if isinstance(method_addr, str):
            method_addr = method_addr.strip()
        rpc_call_id = str(uuid4())[:8]
        self._logger.debug(
            f"{self._config.svc_name} :: [alerts_rpc] call_id={rpc_call_id} "
            f"method_addr={method_addr!r} method_id={method_id} alert_id={alert_id}"
        )
        try:
            res = await self._rpc_exchange.call(method_addr, *params_data)
            if isinstance(res, dict) and res.get("error") is not None:
                self._logger.error(
                    f"{self._config.svc_name} :: Ошибка метода {method_id}: {res.get('error')}"
                )
                return False
        except Exception as ex:
            self._logger.error(
                f"{self._config.svc_name} :: RPC метод {method_id}: {ex!r}"
            )
            return False
        return _truthy_method_result(res)

    async def _apply_complex_alert(
        self,
        r,
        alert_id: str,
        alert_data: dict,
        initiator_point: list,
    ) -> None:
        method_id = alert_data["methodId"]
        ts = initiator_point[0]

        if alert_data["fired"]:
            if ts <= alert_data["fired"]:
                return
            if alert_data["acked"] and ts <= alert_data["acked"]:
                return

        alert_on = await self._eval_complex_method(
            alert_id, method_id, initiator_point
        )

        if (alert_data["fired"] and alert_on) or (
            not alert_data["fired"] and not alert_on
        ):
            return

        if not alert_data["fired"] and alert_on:
            await self._post_message(
                {"alertId": alert_id, "x": ts},
                reply=False,
                routing_key=f"{self._config.hierarchy['class']}.app.alarm_on.{alert_id}",
            )
            alert_data["fired"] = ts
            if alert_data["autoAck"]:
                await self._post_message(
                    {"alertId": alert_id, "x": ts},
                    reply=False,
                    routing_key=f"{self._config.hierarchy['class']}.app.alarm_acked.{alert_id}",
                )
                alert_data["acked"] = ts

        if alert_data["fired"] and not alert_on:
            await self._post_message(
                {"alertId": alert_id, "x": ts},
                reply=False,
                routing_key=f"{self._config.hierarchy['class']}.app.alarm_off.{alert_id}",
            )
            alert_data["fired"] = None
            alert_data["acked"] = None

    async def _tag_value_changed(
        self, mes: dict, routing_key: str = None, id_alert: str = None
    ):
        for tag_item in mes["data"]:
            tag_id = tag_item["tagId"]

            if id_alert is None:
                get_alerts = {
                    "base": tag_id,
                    "scope": CN_SCOPE_ONELEVEL,
                    "filter": {"objectClass": ["prsAlert"], "prsActive": ["TRUE"]},
                    "attributes": ["entryUUID"],
                }
                alerts = await self._hierarchy.search(get_alerts)
            else:
                alerts = [(id_alert, None, None)]

            async with self._cache.get_redis() as r:
                for alert in alerts:
                    alert_id = alert[0]
                    alert_data = await r.json().get(self._alert_cache_key(alert_id))
                    if not alert_data:
                        self._logger.error(
                            f"{self._config.svc_name} :: Нет кэша тревоги {alert_id}."
                        )
                        continue
                    if alert_data.get("kind", "simple") == "complex":
                        continue
                    for data_item in tag_item["data"]:
                        await self._apply_simple_or_duration(
                            r, alert_id, alert_data, data_item
                        )
                        await r.json().set(
                            name=self._alert_cache_key(alert_id),
                            path="$",
                            obj=alert_data,
                        )

            async with self._cache.get_redis() as r:
                ic_map = await r.json().get(self._initiator_complex_key(tag_id))
                if not ic_map:
                    continue
                for alert_id, method_id in ic_map.items():
                    alert_data = await r.json().get(self._alert_cache_key(alert_id))
                    if not alert_data or alert_data.get("kind") != "complex":
                        continue
                    if alert_data.get("methodId") != method_id:
                        continue
                    for data_item in tag_item["data"]:
                        await self._apply_complex_alert(
                            r, alert_id, alert_data, list(data_item)
                        )
                        await r.json().set(
                            name=self._alert_cache_key(alert_id),
                            path="$",
                            obj=alert_data,
                        )

        return NO_AMQP_RPC_REPLY

    async def _schedule_fire_for_complex_alerts(
        self, mes: dict, routing_key: str = None
    ):
        sched_id = mes["id"]
        ts = mes.get("time")
        initiator_point = [ts, None, None]
        async with self._cache.get_redis() as r:
            ic_map = await r.json().get(self._initiator_complex_key(sched_id))
            if not ic_map:
                return NO_AMQP_RPC_REPLY
            for alert_id, method_id in ic_map.items():
                alert_data = await r.json().get(self._alert_cache_key(alert_id))
                if not alert_data or alert_data.get("kind") != "complex":
                    continue
                if alert_data.get("methodId") != method_id:
                    continue
                await self._apply_complex_alert(
                    r, alert_id, alert_data, initiator_point
                )
                await r.json().set(
                    name=self._alert_cache_key(alert_id),
                    path="$",
                    obj=alert_data,
                )
        return NO_AMQP_RPC_REPLY

    async def _get_alerts(self, routing_key: str = None) -> None:
        get_alerts = {
            "filter": {"objectClass": ["prsAlert"], "prsActive": ["TRUE"]},
            "attributes": ["cn", "description", "prsJsonConfigString"],
        }
        alerts = await self._hierarchy.search(get_alerts)
        for alert in alerts:
            await self._make_alert_cache(alert[0])
            await self._bind_alert(alert[0])

    async def on_startup(self) -> None:
        await super().on_startup()
        await self._amqp_consume_queue.unbind(
            self._exchange, "prsTag.app.data_set.*"
        )
        try:
            await self._get_alerts()
        except Exception as ex:
            self._logger.error(f"{self._config.svc_name} :: {ex}")


settings = AlertsAppSettings()

app = AlertsApp(settings=settings, title="`AlertsApp` service")
