"""
Модуль содержит классы, описывающие входные данные для команд CRUD для тегов
и класс сервиса ``tags_api_crud_svc``.
"""
import asyncio
import sys
import json

sys.path.append(".")

from src.common.app_svc import AppSvc
from src.common.amqp_rpc import NO_AMQP_RPC_REPLY
from src.services.alerts.app.alerts_app_settings import AlertsAppSettings
from src.common.hierarchy import CN_SCOPE_ONELEVEL, CN_SCOPE_SUBTREE
import src.common.times as t


def _ts_or_none(value):
    if isinstance(value, bool) or value in (None, 0, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def apply_stored_episode(alert_data: dict, episode: dict | None) -> None:
    """Текущий эпизод из последней строки таблицы тревоги, не из значения тега."""
    if not isinstance(episode, dict):
        return
    start = _ts_or_none(episode.get("x"))
    if start is None:
        return
    acked = _ts_or_none(episode.get("cx"))
    finish = _ts_or_none(episode.get("e"))
    if finish is not None:
        alert_data["fired"] = False
        alert_data["episodeStart"] = start
        alert_data["finish"] = finish
        alert_data["acked"] = acked if acked is not None else False
        return
    alert_data["fired"] = start
    alert_data["episodeStart"] = None
    alert_data["finish"] = None
    alert_data["acked"] = acked if acked is not None else False


def alarm_is_active(alarm: dict) -> bool:
    return _ts_or_none(alarm.get("fired")) is not None


def alarm_is_pending(alarm: dict) -> bool:
    """Пропала и ещё не квитирована."""
    return (
        not alarm_is_active(alarm)
        and _ts_or_none(alarm.get("finish")) is not None
        and _ts_or_none(alarm.get("acked")) is None
    )


def _object_classes(attrs: dict | None) -> set[str]:
    raw = (attrs or {}).get("objectClass") or []
    if isinstance(raw, str):
        raw = [raw]
    classes = set()
    for item in raw:
        if item is None:
            continue
        if isinstance(item, bytes):
            item = item.decode()
        classes.add(str(item))
    return classes


def _dn_under(dn: str | None, parent_dn: str | None) -> bool:
    if not dn or not parent_dn:
        return False
    return dn.lower().endswith("," + parent_dn.lower())


def _query_ts(value):
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value or None
    try:
        return t.ts(value)
    except (TypeError, ValueError):
        return None


def _query_count(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        count = int(value)
    except (TypeError, ValueError):
        return None
    if count < 1:
        return 1
    if count > 500:
        return 500
    return count


def _cache_episodes(alarm: dict) -> list[dict]:
    item = alarm_list_item("", alarm)
    if item["fired"] is None and item["finish"] is None and item["acked"] is None:
        return []
    return [{
        "fired": item["fired"],
        "finish": item["finish"],
        "acked": item["acked"],
    }]


def select_alarm_episodes(
    episodes: list[dict] | None,
    *,
    fired: bool,
    start: int | None,
    finish: int,
    count: int | None,
) -> list[dict]:
    """Отбор эпизодов одной тревоги.

    ``fired=True`` — только эпизод, активный в момент ``finish``. ``count``
    тогда игнорируется. Без ``fired``, ``start`` и ``count`` — состояние
    тревоги в момент ``finish``: последний эпизод, уже начавшийся к этому
    моменту, вместе с его финишем и квитированием. Пустые метки — только
    если к этому моменту тревога ещё ни разу не начиналась.
    ``start`` или ``count`` при ``fired=False`` — список эпизодов со стартом
    в ``[start, finish]``, не больше ``count`` последних (если ``count``
    не задан — не больше 500).
    """
    clean = []
    for row in episodes or []:
        if not isinstance(row, dict):
            continue
        started = _ts_or_none(row.get("fired"))
        if started is None:
            continue
        clean.append({
            "fired": started,
            "finish": _ts_or_none(row.get("finish")),
            "acked": _ts_or_none(row.get("acked")),
        })
    clean.sort(key=lambda row: row["fired"], reverse=True)

    def clip(row: dict) -> dict:
        out = dict(row)
        if out["finish"] is not None and out["finish"] > finish:
            out["finish"] = None
        if out["acked"] is not None and out["acked"] > finish:
            out["acked"] = None
        return out

    def covers(row: dict) -> bool:
        ended = row["finish"]
        return row["fired"] <= finish and (ended is None or ended > finish)

    if fired:
        chosen = next((row for row in clean if covers(row)), None)
        if chosen is None or (start is not None and chosen["fired"] < start):
            return []
        return [clip(chosen)]

    if start is None and count is None:
        chosen = next((row for row in clean if row["fired"] <= finish), None)
        if chosen is None:
            return [{"fired": None, "finish": None, "acked": None}]
        return [clip(chosen)]

    window = [
        row for row in clean
        if row["fired"] <= finish and (start is None or row["fired"] >= start)
    ]
    limit = 500 if count is None else count
    return [clip(row) for row in window[:limit]]


def alarm_list_item(alert_id: str, alarm: dict) -> dict:
    active = alarm_is_active(alarm)
    start = _ts_or_none(alarm.get("fired") if active else alarm.get("episodeStart"))
    finish = None if active else _ts_or_none(alarm.get("finish"))
    return {
        "id": alert_id,
        "cn": alarm.get("cn") or "",
        "description": alarm.get("description") or "",
        "tagId": alarm.get("tagId") or "",
        "fired": start,
        "finish": finish,
        "acked": _ts_or_none(alarm.get("acked")),
    }

class AlertsApp(AppSvc):
    """Сервис работы с тревогами.
    """

    def __init__(self, settings: AlertsAppSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    def _add_app_handlers(self):
        self._handlers[f"{self._config.hierarchy['class']}.app_api.get_alarms"] = self._get_alarms
        self._handlers[f"{self._config.hierarchy['class']}.app_api.ack_alarm"] = self._ack_alarm
        self._handlers["prsTag.app.data_set.*"] = self._tag_value_changed
    async def _deleting(self, mes: dict, routing_key: str = None):
        # перед удалением тревоги
        await self._delete_alert_cache(mes['id'])
        await self._unbind_alert(mes['id'])

    async def _bind_alert(self, alert_id: str):
        # только логика привязки
        # проверка активности тревоги производится вызывающим методом
        # привязка к сообщениям prsAlert.model.* выполняется при старте сервиса и здесь не меняется
        tag_id, _ = await self._hierarchy.get_parent(alert_id)
        await self._amqp_consume_queue.bind(self._exchange, f"prsTag.app.data_set.{tag_id }")

    async def _unbind_alert(self, alert_id: str):
        # если это последняя активная привязанная к тегу тревога,
        # то отписываемся от изменений значений тега
        tag_id, _ = await self._hierarchy.get_parent(alert_id)
        payload = {
            "base": tag_id,
            "scope": CN_SCOPE_SUBTREE,
            "filter": {
                "objectClass": ["prsAlerts"]
            },
            "attributes": ["prsActive"]
        }
        res = await self._hierarchy.search(payload)

        unbind = len(res) == 0
        for alert in res:
            if (alert[0] != alert_id) and (alert[2]["prsActive"][0] == 'TRUE'):
                unbind = False
                break
        if unbind:
            await self._amqp_consume_queue.unbind(self._exchange, f"prsTag.app.data_set.{tag_id }")
            self._logger.info(f"{self._config.svc_name} :: Отвязка от изменений тега {tag_id}")

    async def _created(self, mes: dict, routing_key: str = None):
        # тревога создана
        active = await self._make_alert_cache(mes['id'])
        if active:
            await self._bind_alert(mes['id'])

    async def _updated(self, mes: dict, routing_key: str = None):
        # метод, срабатывающий на изменение экземпляра сущности в иерархии
        # сервис <>.app подписан на это событие по умолчанию

        # поступаем так: удаляем кэш
        # читаем данные по тревоге

        #TODO: не учитываем пока возможности переноса тревоги на другого родителя!

        active = await self._make_alert_cache(mes["id"])
        if active:
            await self._bind_alert(mes['id'])
        else:
            await self._unbind_alert(mes['id'])

    async def _delete_alert_cache(self, alert_id: str):
        async with self._cache.get_redis() as r:
            await r.json().delete(f"{alert_id}.{self._config.svc_name}")

    async def _make_alert_cache(self, alert_id: str) -> bool | None:
        # метод создаёт кэш тревоги и возвращает значение флага prsActive
        # если указанной тревоги нет, то возвращается None
        await self._delete_alert_cache(alert_id=alert_id)

        payload = {
            "id": alert_id,
            "attributes": ['prsActive', 'cn', 'description', 'prsJsonConfigString']
        }
        alert_data = await self._hierarchy.search(payload)
        if not alert_data:
            self._logger.error(f"{self._config.svc_name} :: Нет данных по тревоге {alert_id}.")
            return None
        alert = alert_data[0]

        tag_id, _ = await self._hierarchy.get_parent(alert_id)

        active = alert[2]["prsActive"][0] == 'TRUE'
        if not active:
            self._logger.warning(f"{self._config.svc_name} :: Тревога '{alert_id}' неактивна.")
            return False

        try:
            # json.loads вполне может возвращать целые и вещественные числа,
            # то есть преобразует строку не только в словарь, но и в другие типы
            alert_config = json.loads(alert[2]["prsJsonConfigString"][0])
        except (json.JSONDecodeError, TypeError):
            alert_config = None

        if not isinstance(alert_config, dict):
            self._logger.error(f"{self._config.svc_name} :: У тревоги '{alert_id}' неверная конфигурация.")
            return None
        if (alert_config.get("value") is None) or \
           (alert_config.get("high") is None) or \
           (alert_config.get("autoAck") is None):
            self._logger.error(f"{self._config.svc_name} :: У тревоги '{alert_id}' неверная конфигурация.")
            return None

        alert_data = {
            "tagId": tag_id,
            "alertId": alert_id,
            "fired": False,
            "acked": False,
            "finish": None,
            "episodeStart": None,
            "value": alert_config["value"],
            "high": alert_config["high"],
            "autoAck": alert_config["autoAck"],
            "cn": alert[2]["cn"][0],
            "description": alert[2]["description"][0] or ""
        }
        episode = await self._post_message(
            {"alertId": alert_id},
            reply=True,
            routing_key=f"{self._config.hierarchy['class']}.app.alarm_state.{alert_id}",
            timeout=1.0,
        )
        apply_stored_episode(alert_data, episode if isinstance(episode, dict) else None)

        async with self._cache.get_redis() as r:
            await r.json().set(
                name=f"{alert_id}.{self._config.svc_name}", path="$", obj=alert_data
            )

        # проведём активацию тревоги ---------------
        payload = {
            "tagId": tag_id,
            "actual": True
        }
        res = await self._post_message(
            mes=payload,
            reply=True,
            routing_key=f"prsTag.app_api_client.data_get.{tag_id}"
        )
        if not res is None:
            if res.get('data'):
                await self._tag_value_changed(res, id_alert=alert_id)
            else:
                self._logger.warning(f"{self._config.svc_name} :: Тег {tag_id} не имеет данных.")
            return True
        else:
            self._logger.warning(f"{self._config.svc_name} :: Тег {tag_id} не привязан к хранилищу.")
            return True

    async def _root_base(self, name: str) -> str:
        dn = f"cn={name},cn=prs"
        getter = getattr(self._hierarchy, "get_node_id", None)
        if getter is None:
            return dn
        try:
            node_id = await getter(dn)
        except Exception:
            return dn
        return node_id or dn

    async def _search_nodes(self, base: str | None, scope: int, object_class: str) -> list:
        payload = {
            "scope": scope,
            "filter": {
                "objectClass": [object_class],
                "prsActive": [True],
            },
            "attributes": ["cn", "objectClass"],
        }
        if base:
            payload["base"] = base
        found = await self._hierarchy.search(payload)
        return found or []

    async def _lookup_node(self, node_id: str):
        found = await self._hierarchy.search({
            "id": node_id,
            "attributes": ["objectClass", "cn"],
        })
        return found[0] if found else None

    def _without_child_objects(self, alerts: list, child_objects: list) -> list:
        child_dns = [row[1] for row in child_objects if row[1]]
        if not child_dns:
            return alerts
        kept = []
        for alert in alerts:
            dn = alert[1]
            if any(_dn_under(dn, child) for child in child_dns):
                continue
            kept.append(alert)
        return kept

    async def _alarms_of_object(self, object_id: str, get_children: bool) -> list:
        if get_children:
            return await self._search_nodes(object_id, CN_SCOPE_SUBTREE, "prsAlert")
        alerts = await self._search_nodes(object_id, CN_SCOPE_SUBTREE, "prsAlert")
        # Вложенный объект может лежать в папке, не прямым потомком.
        descendants = await self._search_nodes(object_id, CN_SCOPE_SUBTREE, "prsObject")
        descendants = [row for row in descendants if row[0] != object_id]
        return self._without_child_objects(alerts, descendants)

    async def _alarms_for_parent(self, parent: str, get_children: bool) -> list:
        node = await self._lookup_node(parent)
        classes = _object_classes(node[2]) if node else set()
        if "prsAlert" in classes:
            return [node]
        if "prsTag" in classes:
            scope = CN_SCOPE_SUBTREE if get_children else CN_SCOPE_ONELEVEL
            return await self._search_nodes(parent, scope, "prsAlert")
        if "prsObject" in classes:
            return await self._alarms_of_object(parent, get_children)
        scope = CN_SCOPE_SUBTREE if get_children else CN_SCOPE_ONELEVEL
        return await self._search_nodes(parent, scope, "prsAlert")

    async def _top_level_objects(self, objects_root: str) -> list:
        objects = await self._search_nodes(objects_root, CN_SCOPE_SUBTREE, "prsObject")
        top = []
        for obj in objects:
            dn = obj[1]
            if any(
                other[0] != obj[0] and _dn_under(dn, other[1])
                for other in objects
            ):
                continue
            top.append(obj)
        return top

    async def _alarm_scope(self, parents: list[str] | None, get_children: bool) -> list:
        if not parents:
            objects_root = await self._root_base("objects")
            tags_root = await self._root_base("tags")
            if get_children:
                rows = await self._search_nodes(objects_root, CN_SCOPE_SUBTREE, "prsAlert")
                rows += await self._search_nodes(tags_root, CN_SCOPE_SUBTREE, "prsAlert")
            else:
                rows = []
                for obj in await self._top_level_objects(objects_root):
                    rows += await self._alarms_of_object(obj[0], False)
                rows += await self._search_nodes(tags_root, CN_SCOPE_SUBTREE, "prsAlert")
        else:
            rows = []
            for parent in parents:
                rows += await self._alarms_for_parent(parent, get_children)
        found = []
        seen = set()
        for row in rows:
            if not row or row[0] in seen:
                continue
            seen.add(row[0])
            found.append(row)
        return found

    async def _read_alarm_episodes(
        self,
        alert_id: str,
        start: int | None,
        finish: int,
        count: int,
    ) -> list:
        body = {"alertId": alert_id, "finish": finish, "count": count}
        if start is not None:
            body["start"] = start
        try:
            res = await self._post_message(
                body,
                reply=True,
                timeout=5.0,
                routing_key=f"{self._config.hierarchy['class']}.app.alarm_history.{alert_id}",
            )
        except Exception as ex:
            self._logger.error(
                f"{self._config.svc_name} :: История тревоги {alert_id} не прочитана: {ex}"
            )
            return []
        if not isinstance(res, dict):
            return []
        data = res.get("data")
        return data if isinstance(data, list) else []

    async def _get_alarms(self, mes: dict, routing_key: str = None) -> dict:
        """Алярмы по правилам ``AlarmsGet``.

        ``fired`` (по умолчанию да) — эпизод, активный в момент ``finish``.
        ``finish`` по умолчанию — текущее время. ``count`` при ``fired``
        не используется. Без ``fired``, ``start`` и ``count`` возвращается
        состояние каждой тревоги на момент ``finish``: последний эпизод,
        уже начавшийся к этому моменту, в том числе закончившийся и
        квитированный. ``start`` или ``count`` без ``fired`` — список
        эпизодов.
        """
        parents = mes.get("parentId")
        if isinstance(parents, str):
            parents = [parents]
        elif parents is not None and not isinstance(parents, list):
            parents = [parents]
        get_children = bool(mes.get("getChildren"))
        fired_only = bool(mes.get("fired", True))
        start = _query_ts(mes.get("start"))
        finish = _query_ts(mes.get("finish"))
        count = None if fired_only else _query_count(mes.get("count"))
        now = t.now_int()
        point = now if finish is None else finish
        # Текущее состояние уже лежит в кэше. Таблица нужна для прошлого
        # момента и для списка эпизодов.
        use_history = start is not None or point < now or count is not None
        alerts = await self._alarm_scope(parents, get_children)
        result = {"data": []}
        prepared = []
        async with self._cache.get_redis() as r:
            for alert in alerts:
                alarm = await r.json().get(f"{alert[0]}.{self._config.svc_name}")
                if not isinstance(alarm, dict):
                    self._logger.error(f"{self._config.svc_name} :: Нет кэша для тревоги {alert[0]}")
                    continue
                if not alarm.get("tagId"):
                    try:
                        tag_id, _ = await self._hierarchy.get_parent(alert[0])
                        alarm["tagId"] = tag_id
                    except Exception:
                        alarm["tagId"] = ""
                prepared.append((alert[0], alarm))

        if use_history:
            fetch_count = count or 500
            histories = await asyncio.gather(*(
                self._read_alarm_episodes(alert_id, start, point, fetch_count)
                for alert_id, _alarm in prepared
            ))
        else:
            histories = [_cache_episodes(alarm) for _alert_id, alarm in prepared]

        for (alert_id, alarm), episodes in zip(prepared, histories):
            rows = select_alarm_episodes(
                episodes,
                fired=fired_only,
                start=start,
                finish=point,
                count=count,
            )
            for row in rows:
                result["data"].append({
                    "id": alert_id,
                    "cn": alarm.get("cn") or "",
                    "description": alarm.get("description") or "",
                    "tagId": alarm.get("tagId") or "",
                    "fired": row.get("fired"),
                    "finish": row.get("finish"),
                    "acked": row.get("acked"),
                })
        return result

    async def _ack_alarm(self, mes: dict, routing_key: str = None):
        """_summary_

        Args:
            mes (dict): {
                "id": "alert_id",
                "x": 123
            }
        """
        alert_id = mes["id"]
        raw_x = mes.get("x")
        try:
            x = t.ts(raw_x) if raw_x else t.now_int()
        except (TypeError, ValueError):
            x = t.now_int()
        alert_cache_key = f"{alert_id}.{self._config.svc_name}"
        async with self._cache.get_redis() as r:
            alert_data = await r.json().get(name=alert_cache_key)

            if not alert_data:
                self._logger.error(f"{self._config.svc_name} :: Отсутствует кэш по тревоге {alert_id}.")
                return

            active = alarm_is_active(alert_data)
            pending = alarm_is_pending(alert_data)
            if _ts_or_none(alert_data.get("acked")) is not None:
                self._logger.warning(f"{self._config.svc_name} :: Тревога {alert_id} уже квитирована.")
                return
            if not active and not pending:
                self._logger.warning(f"{self._config.svc_name} :: Тревога {alert_id} неактивна.")
                return

            # Активная получает метку квитирования. Пропавшая остаётся в кэше
            # последним эпизодом: старт, финиш и эта метка.
            alert_data["acked"] = x
            await r.json().set(name=alert_cache_key, path="$", obj=alert_data)

        await self._post_message(
            {
                "alertId": alert_id,
                "x": x
            },
            reply=False,
            routing_key=f"{self._config.hierarchy['class']}.app.alarm_acked.{alert_id}"
        )

    async def _tag_value_changed(self, mes: dict, routing_key: str = None, id_alert: str = None):
        """_summary_

        Args:
            mes (dict): {
                "data": [
                    {
                        "tagId": "...",
                        "data": [
                            (1, 2, 3)
                        ]
                    }
                ]
            }
        """
        for tag_item in mes["data"]:
            tag_id = tag_item["tagId"]

            if id_alert is None:
                get_alerts = {
                    "base": tag_id,
                    "scope": CN_SCOPE_ONELEVEL,
                    "filter": {
                        "objectClass": ["prsAlert"],
                        "prsActive": [True]
                    },
                    "attributes": ["entryUUID"]
                }
                alerts = await self._hierarchy.search(get_alerts)
            else:
                alerts = [(id_alert, None, None)]

            async with self._cache.get_redis() as r:
                for alert in alerts:
                    alert_id = alert[0]
                    alert_data = await r.json().get(
                        f"{alert_id}.{self._config.svc_name}"
                    )

                    if not alert_data:
                        self._logger.error(f"{self._config.svc_name} :: Нет кэша тревоги {alert_id}.")
                        continue

                    for data_item in tag_item["data"]:

                        # если данные более ранние, чем уже обработанные...
                        if alert_data["fired"]:
                            if data_item[0] <= alert_data["fired"]:
                                continue
                            if alert_data["acked"] and (data_item[0] <= alert_data["acked"]):
                                continue

                        alert_on = (
                            data_item[1] < alert_data["value"],
                            data_item[1] >= alert_data["value"],
                        )[alert_data["high"]]

                        self._logger.debug(f"Alarm on: {alert_on}")

                        if (alert_data["fired"] and alert_on) or \
                            (not alert_data["fired"] and not alert_on):
                            continue

                        if not alert_data["fired"] and alert_on:
                            await self._post_message(
                                {
                                    "alertId": alert_id,
                                    "x": data_item[0]
                                },
                                reply=False,
                                routing_key=f"{self._config.hierarchy['class']}.app.alarm_on.{alert_id}"
                            )
                            alert_data["fired"] = data_item[0]
                            alert_data["finish"] = None
                            alert_data["episodeStart"] = None
                            alert_data["acked"] = False

                            if alert_data["autoAck"]:
                                await self._post_message(
                                    {
                                        "alertId": alert_id,
                                        "x": data_item[0]
                                    },
                                    reply=False,
                                    routing_key=f"{self._config.hierarchy['class']}.app.alarm_acked.{alert_id}"
                                )
                                alert_data["acked"] = data_item[0]


                        if alert_data["fired"] and not alert_on:
                            await self._post_message(
                                {
                                    "alertId": alert_id,
                                    "x": data_item[0]
                                },
                                reply=False,
                                routing_key=f"{self._config.hierarchy['class']}.app.alarm_off.{alert_id}"
                            )
                            alert_data["episodeStart"] = alert_data["fired"]
                            alert_data["finish"] = data_item[0]
                            alert_data["fired"] = False

                    await r.json().set(
                        name=f"{alert_id}.{self._config.svc_name}", path="$", obj=alert_data
                    )

        # Ответ на RPC не шлём: запись в хранилище отвечает dataStorages (см. base_svc).
        return NO_AMQP_RPC_REPLY

    async def _get_alerts(self, routing_key: str = None) -> None:
        get_alerts = {
            "filter": {
                "objectClass": ["prsAlert"],
                "prsActive": [True]
            },
            "attributes": ["cn", "description", "prsJsonConfigString"]
        }
        alerts = await self._hierarchy.search(get_alerts)
        for alert in alerts:
            await self._make_alert_cache(alert[0])
            await self._bind_alert(alert[0])

    async def on_startup(self) -> None:
        await super().on_startup()

        # по умолчанию очередь привязывается к изменениям всех тегов
        # нам же нужны только изменения тегов, у которых есть тревоги
        await self._amqp_consume_queue.unbind(self._exchange, "prsTag.app.data_set.*")
        try:
            await self._get_alerts()
        except Exception as ex:
            self._logger.error(f"{self._config.svc_name} :: {ex}")

settings = AlertsAppSettings()

app = AlertsApp(settings=settings, title="`TagsApp` service")
