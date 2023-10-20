import sys
import json
import asyncio
import numbers
import copy
from typing import Any, List, Tuple
import pandas as pd
from pandas.api.types import is_numeric_dtype
import numpy as np
import time

sys.path.append(".")

from dataStorages_app_postgresql_settings import DataStoragesAppPostgreSQLSettings
from src.common import svc
import src.common.times as t
from src.common.consts import (
    CNTagValueTypes as TVT,
    Order
)

import asyncpg as apg
from asyncpg.exceptions import PostgresError

def linear_interpolated(start_point: Tuple[int, Any],
                        end_point: Tuple[int, Any],
                        x: int):
    """ Получение линейно интерполированного значения по двум точкам.
    Если в качестве координат `y` переданы нечисловые значения, возвращается
    start_point[1]

    :param start_point: Кортеж координат начальной точки
    :type start_point: Tuple[int, Any]
    :param end_point: Кортеж координат конечной точки
    :type end_point: Tuple[int, Any]
    :param x: координата x точки, для которой надо получить интерполированное значение
    :type x: int
    :param return_type: Тип возвращаемого значения
    :type return_type: int

    :return: Интерполированное значение
    :rtype: Any
    """
    x0, y0 = start_point
    x1, y1 = end_point
    if not isinstance(y0, numbers.Number) or not isinstance(y1, numbers.Number):
        return y0

    if y0 == y1:
        return y0

    if x0 == x1:
        return y0

    return (x-x0)/(x1-x0)*(y1-y0)+y0

class DataStoragesAppPostgreSQL(svc.Svc):

    def __init__(
            self, settings: DataStoragesAppPostgreSQLSettings, *args, **kwargs
        ):
        super().__init__(settings, *args, **kwargs)

        self._connection_pools = {}
        self._tags = {}
        self._alerts = {}
        self._data_cache = {}

    def _set_incoming_commands(self) -> dict:
        return {
            "tags.downloadData": self._tag_get,
            "tags.uploadData": self._tag_set,
            #"alerts.getAlarms": self._get_alarms,
            "alerts.alarmAcked": self._alarm_ack,
            "alerts.alarmOn": self._alarm_on,
            "alerts.alarmOff": self._alarm_off,
            "dataStorages.linkTag": self._link_tag,
            "dataStorages.unlinkTag": self._unlink_tag,
            "dataStorages.linkAlert": self._link_alert,
            "dataStorages.unlinkTag": self._unlink_alert,
            "dataStorages.unlinkTag": self._updated,
        }

    async def _updated(self, mes: dict) -> None:
        pass

    async def _alarm_on(self, mes: dict) -> None:
        """Факт возникновения тревоги.

        Args:
            mes (dict): {
                "action": "alerts.alarmOn",
                "data": {
                    "alertId": "alert_id",
                    "x": 123
                }
            }
        """
        self._logger.debug(f"Обработка возникновения тревоги: {mes}")

        alert_id = mes["data"]["alertId"]

        alert_params = self._alerts.get(alert_id)
        if not alert_params:
            self._logger.error(
                f"Тревога {alert_id} не привязана к хранилищу."
            )
            return

        connection_pool = alert_params["ds"]
        alert_tbl = alert_params["table"]

        try:
            records = []
            async with connection_pool.acquire() as conn:
                async with conn.transaction():
                    q = [f'select * from \"{alert_tbl}\" order by x desc limit 1;']
                    async for r in conn.cursor(*q):
                        records.append((r.get('id'), r.get('x'), r.get('cx'), r.get('e')))

                    # если алярмов у тревоги вообще нет или закончились...
                    if not records or records[0][0] is None or records[0][3]:
                        await conn.copy_records_to_table(
                            alert_tbl,
                            records=[(mes["data"]["x"], None, None)],
                            columns=('x', 'cx', 'e'))

                        await self._post_message(mes={
                                "action": "dataStorages.alertOnArchived",
                                "data": mes["data"]
                            },
                            reply=False, routing_key=alert_id
                        )

                        self._logger.debug(f"Тревога {alert_id} зафиксирована.")
                    else:
                        self._logger.debug(f"Тревога {alert_id} уже активна.")

        except PostgresError as ex:
            self._logger.error(f"Ошибка при записи данных тревоги {alert_id}: {ex}")

    async def _alarm_ack(self, mes: dict) -> None:
        """Факт квитирования тревоги.

        Args:
            mes (dict): {
                "action": "alerts.alarmAcked",
                "data": {
                    "alertId": "alert_id",
                    "x": 123
                }
            }
        """
        self._logger.debug(f"Обработка квитирования тревоги: {mes}")

        alert_id = mes["data"]["alertId"]

        alert_params = self._alerts.get(alert_id)
        if not alert_params:
            self._logger.error(
                f"Тревога {alert_id} не привязана к хранилищу."
            )
            return

        connection_pool = alert_params["ds"]
        alert_tbl = alert_params["table"]

        try:
            records = []
            async with connection_pool.acquire() as conn:
                async with conn.transaction():
                    q = [f'select * from \"{alert_tbl}\" order by x desc limit 1;']
                    async for r in conn.cursor(*q):
                        records.append((r.get('id'), r.get('x'), r.get('cx'), r.get('e')))

                    # если алярмов у тревоги вообще нет или уже квитирована...
                    if records[0][0] is None or records[0][2]:
                        self._logger.debug(f"Тревоги {alert_id} нет, либо уже квитирована.")
                        return

                    q = f"update \"{alert_tbl}\" set cx = {mes['data']['x']}"
                    await conn.execute(q)
                    await self._post_message(mes={
                            "action": "dataStorages.alertAckArchived",
                            "data": mes["data"]
                        },
                        reply=False, routing_key=alert_id
                    )

                    self._logger.debug(f"Тревога {alert_id} квитирована.")

        except PostgresError as ex:
            self._logger.error(f"Ошибка при записи данных тревоги {alert_id}: {ex}")

    async def _alarm_off(self, mes: dict) -> None:
        """Факт пропадания тревоги.

        Args:
            mes (dict): {
                "action": "alerts.alrmOff",
                "data": {
                    "alertId": "alert_id",
                    "x": 123
                }
            }
        """
        self._logger.debug(f"Обработка пропадания тревоги: {mes}")

        alert_id = mes["data"]["alertId"]

        alert_params = self._alerts.get(alert_id)
        if not alert_params:
            self._logger.error(
                f"Тревога {alert_id} не привязана к хранилищу."
            )
            return

        connection_pool = alert_params["ds"]
        alert_tbl = alert_params["table"]

        try:
            records = []
            async with connection_pool.acquire() as conn:
                async with conn.transaction():
                    q = [f'select * from \"{alert_tbl}\" order by x desc limit 1;']
                    async for r in conn.cursor(*q):
                        records.append((r.get('id'), r.get('x'), r.get('cx'), r.get('e')))

                    # если алярмов у тревоги вообще нет или закончились...
                    if records[0][0] is None or records[0][3]:
                        self._logger.debug(f"Нет активной тревоги {alert_id}.")
                        return

                    q = f"update \"{alert_tbl}\" set e = {mes['data']['x']}"
                    await conn.execute(q)
                    await self._post_message(mes={
                            "action": "dataStorages.alertOffArchived",
                            "data": mes["data"]
                        },
                        reply=False, routing_key=alert_id
                    )

                    self._logger.debug(f"Тревога {alert_id} закончена.")

        except PostgresError as ex:
            self._logger.error(f"Ошибка при записи данных тревоги {alert_id}: {ex}")

    async def _reject_message(self, mes: dict) -> bool:
        return False

    async def _link_tag(self, mes: dict) -> dict:
        """Метод привязки тега к хранилищу.
        Атрибут ``prsStore`` должен быть вида
        ``{"tableName": "<some_table>"}`` либо отсутствовать

        Args:
            mes (dict): {
                "action": "dataStorages.linkTag",
                "data": {
                    "tagId": "tag_id",
                    "dataStorageId": "ds_id",
                    "attributes": {
                        "prsStore": {"tableName": "<some_table>"}
                    }
                }

        """

        async with self._connection_pools[mes["data"]["dataStorageId"]].acquire() as conn:

            if not mes["data"]["attributes"].get("prsStore"):
                mes["data"]["attributes"]["prsStore"] = \
                    {"tableName": f't_{mes["data"]["tagId"]}'}

            tag_params = self._tags.get(mes["data"]["tagId"])
            if tag_params:
                tbl_name = tag_params['table']
                if mes["data"]["attributes"]["prsStore"]["tableName"] == tbl_name:
                    self._logger.warning(f"Тег {mes['data']['tagId']} уже привязан")
                    return

                await conn.execute(
                    f'drop table if exists "{tbl_name}"'
                )

            tbl_name = mes["data"]["attributes"]["prsStore"]["tableName"]

            tag_cache = await self._prepare_tag_data(
                mes["data"]["tagId"],
                mes["data"]["dataStorageId"]
            )
            tag_cache["table"] = tbl_name
            cache_for_store = copy.deepcopy(tag_cache)

            tag_cache["ds"] = self._connection_pools[mes["data"]["dataStorageId"]]
            match tag_cache["value_type"]:
                case TVT.CN_INT:
                    s_type = "bigint"
                case TVT.CN_DOUBLE:
                    s_type = "double precision"
                case TVT.CN_STR:
                    s_type = "text"
                case TVT.CN_JSON:
                    s_type = "jsonb"
                case _:
                    er_str = f"Тег: {mes['data']['tagId']}; неизвестный тип данных: {tag_cache['value_type']}"
                    self._logger.error(er_str)
                    return

            query = (f'CREATE TABLE public."{tag_cache["table"]}" ('
                    f'"id" serial primary key,'
                    f'"x" bigint NOT NULL,'
                    f'"y" {s_type},'
                    f'"q" int);'
                    # Создание индекса на поле "метка времени" ("ts")
                    f'CREATE INDEX "{tag_cache["table"]}_idx" ON public."{tag_cache["table"]}" '
                    f'USING btree ("x");')

            if tag_cache["value_type"] == 4:
                query += (f'CREATE INDEX "{tag_cache["table"]}_json__idx" ON public."{tag_cache["table"]}" '
                            'USING gin ("y" jsonb_path_ops);')

            await conn.execute(query)

            self._tags[mes["data"]["tagId"]] = tag_cache


        return {
            "prsStore": json.dumps(cache_for_store)
        }

    async def _link_alert(self, mes: dict) -> dict:
        """Метод привязки тревоги к хранилищу.
        Атрибут ``prsStore`` должен быть вида
        ``{"tableName": "<some_table>"}`` либо отсутствовать

        Args:
            mes (dict): {
                "action": "dataStorages.linkAlert",
                "data": {
                    "alertId": "alert_id",
                    "dataStorageId": "ds_id",
                    "attributes": {
                        "prsStore": {"tableName": "<some_table>"}
                    }
                }

        """

        async with self._connection_pools[mes["data"]["dataStorageId"]].acquire() as conn:

            if not mes["data"]["attributes"].get("prsStore"):
                mes["data"]["attributes"]["prsStore"] = \
                    {"tableName": f'a_{mes["data"]["alertId"]}'}

            alert_params = self._alerts.get(mes["data"]["alertId"])
            if alert_params:
                tbl_name = alert_params['table']
                if mes["data"]["attributes"]["prsStore"]["tableName"] == tbl_name:
                    self._logger.warning(f"Тревога {mes['data']['alertId']} уже привязана.")
                    return

                await conn.execute(
                    f'drop table if exists "{tbl_name}"'
                )

            tbl_name = mes["data"]["attributes"]["prsStore"]["tableName"]

            alert_cache = await self._prepare_alert_data(
                mes["data"]["alertId"],
                mes["data"]["dataStorageId"]
            )
            alert_cache["table"] = tbl_name
            cache_for_store = copy.deepcopy(alert_cache)

            alert_cache["ds"] = self._connection_pools[mes["data"]["dataStorageId"]]

            query = (f'CREATE TABLE public."{alert_cache["table"]}" ('
                    f'"id" serial primary key,'
                    f'"x" bigint NOT NULL,' # время возникновения тревоги
                    f'"cx" bigint,'         # время квитирования
                    f'"e" bigint);'         # время пропадания тревоги
                    # Создание индекса на поле "метка времени" ("ts")
                    f'CREATE INDEX "{alert_cache["table"]}_idx" ON public."{alert_cache["table"]}" '
                    f'USING btree ("x");')

            await conn.execute(query)

            self._alerts[mes["data"]["alertId"]] = alert_cache


        return {
            "prsStore": json.dumps(cache_for_store)
        }

    async def _unlink_alert(self, mes: dict) -> None:
        """_summary_

        Args:
            mes (dict): {
                "action": "dataStorages.unlinkAlert",
                "data": {
                    "alertId": "alert_id"
                }
        """
        alert_params = self._tags.get(mes["data"]["alertId"])
        if not alert_params:
            self._logger.warning(f"Тревога {mes['data']['alertId']} не привязана к хранилищу.")
            return

        async with alert_params["ds"].acquire() as conn:
            await conn.execute(
                f'drop table if exists "{alert_params["table"]}"'
            )

        self._alerts.pop(mes["data"]["alertId"])

        self._logger.info(f"Тревога {mes['data']['alertId']} отвязана от хранилища.")

    async def _unlink_tag(self, mes: dict) -> None:
        """_summary_

        Args:
            mes (dict): {
                "action": "datastorages.unlinktag",
                "data": {
                    "id": "tag_id"
                }
        """
        tag_params = self._tags.get(mes["data"]["tagId"])
        if not tag_params:
            self._logger.warning(f"Тег {mes['data']['tagId']} не привязан к хранилищу.")
            return

        async with tag_params["ds"].acquire() as conn:
            await conn.execute(
                f'drop table if exists "{tag_params["table"]}"'
            )

        self._tags.pop(mes["data"]["tagId"])

        self._logger.info(f"Тег {mes['data']['tagId']} отвязан от хранилища.")

    async def _write_cache_data(self) -> None:

        for ds_id, tags in self._data_cache.items():
            self._logger.info(f"Запись данных из кэша в базу {ds_id}...")
            connection_pool = self._connection_pools[ds_id]
            try:
                async with connection_pool.acquire() as conn:
                    for tag_id, data in tags.items():
                        tag_params = self._tags[tag_id]
                        tag_tbl = tag_params["table"]

                        if data:
                            async with conn.transaction(isolation='read_committed'):
                                if tag_params["update"]:
                                    xs = [str(x) for _, x, _ in data]
                                    q = f'delete from "{tag_tbl}" where x in ({",".join(xs)}); '
                                    await conn.execute(q)
                                if tag_params["value_type"] == 4:
                                    new_data = []
                                    for item in data:
                                        new_data.append(
                                            (json.dumps(item[0], ensure_ascii=False), item[1], item[2])
                                        )
                                    data = new_data

                                await conn.copy_records_to_table(
                                    tag_tbl,
                                    records=data,
                                    columns=('y', 'x', 'q'))
                            self._logger.debug(f"В базу {ds_id} для тега {tag_id} записано {len(data)} точек.")
                            tags[tag_id] = []
                        else:
                            self._logger.debug(f"Для тега {tag_id} в кэше нет данных.")

            except Exception as ex:
                self._logger.error(f"Ошибка записи данных в базу {ds_id}: {ex}")

        loop = asyncio.get_event_loop()
        loop.call_later(self._config.cache_data_period, lambda: asyncio.create_task(self._write_cache_data()))

    async def _tag_set(self, mes: dict) -> None:
        """

        Args:
            mes (dict): {
                "action": "tags.set_data",
                "data": {
                    "data": [
                        {
                            "tagId": "<some_id>",
                            "data": [(y,x,q)]
                        }
                    ]
                }
            }
        """
        for tag_data in mes["data"]["data"]:
            tag_params = self._tags[tag_data["tagId"]]
            self._data_cache[tag_params["ds_id"]][tag_data["tagId"]].extend(tag_data["data"])

    async def _prepare_tag_data(self, tag_id: str, ds_id: str) -> dict | None:
        get_tag_data = {
            "id": [tag_id],
            "attributes": [
                "prsUpdate", "prsValueTypeCode", "prsActive", "prsStep"
            ]
        }

        tag_data = await self._hierarchy.search(payload=get_tag_data)

        if not tag_data:
            self._logger.info(f"Не найден тег {tag_id}")
            return None

        to_return = {
            "table": None,
            "active": tag_data[0][2]["prsActive"][0] == "TRUE",
            "update": tag_data[0][2]["prsUpdate"][0] == "TRUE",
            "value_type": int(tag_data[0][2]["prsValueTypeCode"][0]),
            "step": tag_data[0][2]["prsStep"][0] == "TRUE"
        }

        get_link_data = {
            "base": ds_id,
            "filter": {
                "cn": [tag_id]
            },
            "attributes": ["prsStore"]
        }

        link_data = await self._hierarchy.search(payload=get_link_data)

        if not link_data:
            return to_return

        to_return["table"] = json.loads(link_data[0][2]["prsStore"][0])["table"]

        return to_return

    async def _prepare_alert_data(self, alert_id: str, ds_id: str) -> dict | None:
        get_alert_data = {
            "id": [alert_id],
            "attributes": [
                "prsActive"
            ]
        }

        alert_data = await self._hierarchy.search(payload=get_alert_data)

        if not alert_data:
            self._logger.info(f"Не найдена тревога {alert_id}")
            return None

        to_return = {
            "table": None,
            "active": alert_data[0][2]["prsActive"][0] == "TRUE"
        }

        get_link_data = {
            "base": ds_id,
            "filter": {
                "cn": [alert_id]
            },
            "attributes": ["prsStore"]
        }

        link_data = await self._hierarchy.search(payload=get_link_data)

        if not link_data:
            return to_return

        to_return["table"] = json.loads(link_data[0][2]["prsStore"][0])["table"]

        return to_return

    async def _connect_to_db(self) -> None:
        if not self._config.datastorages_id:
            ds_node_id = await self._hierarchy.get_node_id("cn=dataStorages,cn=prs")
            payload = {
                "base": ds_node_id,
                "filter": {
                    "prsEntityTypeCode": [self._config.datastorage_type],
                    "objectClass": ["prsDataStorage"]
                }
            }
        else:
            payload = {
                "id": self._config.datastorages_id
            }
            # если указаны конкретные id хранилищ, которые надо обслуживать,
            # то отменяем базовую привязку очереди прослушивания
            await self._amqp_consume["queue"].unbind(
                    exchange=self._amqp_consume["exchanges"]["main"]["exchange"],
                    routing_key=self._config.consume["exchanges"]["main"]["routing_key"][0]
                )

        payload["attributes"] = ["prsJsonConfigString"]

        dss = await self._hierarchy.search(payload=payload)
        for ds in dss:
            await self._amqp_consume["queue"].bind(
                exchange=self._amqp_consume["exchanges"]["main"]["exchange"],
                routing_key=ds[0]
            )

            self._logger.info(f"Чтение данных о хранилище {ds[0]}...")

            dsn = json.loads(ds[2]["prsJsonConfigString"][0])["dsn"]

            connected = False
            while not connected:
                try:
                    self._connection_pools[ds[0]] = await apg.create_pool(dsn=dsn)
                    self._logger.info(f"Связь с базой данных {ds[0]} установлена.")
                    connected = True
                except Exception as ex:
                    self._logger.error(f"Ошибка связи с базой данных '{ds[0]}': {ex}")
                    await asyncio.sleep(5)

            search_tags = {
                "base": ds[0],
                "filter": {
                    "objectClass": ["prsDatastorageTagData"]
                },
                "attributes": ["prsStore", "cn"]
            }

            self._logger.info("Чтение тегов, привязанных к хранилищу...")

            self._data_cache[ds[0]] = {}

            i = 1
            #async for tag in self._hierarchy.search(payload=search_tags):
            tags = await self._hierarchy.search(payload=search_tags)
            for tag in tags:
                self._logger.debug(f"Текущий тег: {tag}")

                '''
                if not tag[0]:
                    continue
                '''

                t1 = time.time()

                tag_id = tag[2]["cn"][0]

                self._logger.debug(f"Подготовка кэша тега.")
                tag_cache = json.loads(tag[2]["prsStore"][0])
                if not tag_cache:
                    self._logger.debug(f"Кэш пустой.")
                    continue

                self._logger.debug(f"Сохранение кэша тега.")
                tag_cache["ds"] = self._connection_pools[ds[0]]
                tag_cache["ds_id"] = ds[0]
                self._tags[tag_id] = tag_cache

                self._data_cache[ds[0]][tag_id] = []

                self._logger.debug(f"Привязка очереди.")
                await self._amqp_consume["queue"].bind(
                    exchange=self._amqp_consume["exchanges"]["tags"]["exchange"],
                    routing_key=tag_id
                )

                self._logger.debug(f"Тег {tag_id} привязан ({i}). Время: {time.time() - t1}")
                i += 1

            self._logger.info(f"Хранилище {ds[0]}. Теги прочитаны.")

            search_alerts = {
                "base": ds[0],
                "filter": {
                    "objectClass": ["prsDatastorageAlertData"]
                },
                "attributes": ["prsStore", "cn"]
            }

            self._logger.info("Чтение тревог, привязанных к хранилищу...")

            #async for alert in self._hierarchy.search(payload=search_alerts):
            alerts = await self._hierarchy.search(payload=search_alerts)
            for alert in alerts:
                self._logger.debug(f"Текущая тревога: {alert}")

                t1 = time.time()

                alert_id = alert[2]["cn"][0]

                self._logger.debug(f"Подготовка кэша тревоги.")
                alert_cache = json.loads(alert[2]["prsStore"][0])
                if not alert_cache:
                    self._logger.debug(f"Кэш пустой.")
                    continue

                self._logger.debug(f"Сохранение кэша тревоги.")
                alert_cache["ds"] = self._connection_pools[ds[0]]
                self._alerts[alert_id] = alert_cache

                self._logger.debug(f"Привязка очереди.")
                await self._amqp_consume["queue"].bind(
                    exchange=self._amqp_consume["exchanges"]["alerts"]["exchange"],
                    routing_key=alert_id
                )

                self._logger.debug(f"Тревога {alert_id} привязана ({i}). Время: {time.time() - t1}")
                i += 1

            self._logger.info(f"Хранилище {ds[0]}. Тревоги прочитаны.")

    async def on_startup(self) -> None:
        await super().on_startup()
        try:
            await self._connect_to_db()

            loop = asyncio.get_event_loop()
            loop.call_later(self._config.cache_data_period, lambda: asyncio.create_task(self._write_cache_data()))

            #await asyncio.gather(asyncio.create_task())
        except Exception as ex:
            self._logger.error(f"Ошибка связи с базой данных: {ex}")

    async def _tag_get(self, mes: dict) -> dict:
        """_summary_

        Args:
            mes (dict): {
                "action": "tags.get_data",
                "data": {
                    "tagId": [str],
                    "start": int,
                    "finish": int,
                    "maxCount": int,
                    "format": bool,
                    "actual": bool,
                    "value": Any,
                    "count": int,
                    "timeStep": int
                }
            }

        Returns:
            _type_: _description_
        """

        self._logger.debug(f"mes: {mes}")

        tasks = {}
        for tag_id in mes["data"]["tagId"]:
            tag_params = self._tags.get(tag_id)
            if not tag_params:
                self._logger.error(
                    f"Тег {tag_id} не привязан к хранилищу."
                )
                continue

            # Если ключ actual установлен в true, ключ timeStep не учитывается
            if mes["data"]["actual"] or (mes["data"]["value"] is not None \
               and len(mes["data"]["value"]) > 0):
                mes["data"]["timeStep"] = None

            if mes["data"]["actual"]:
                self._logger.debug(f"Create task 'data_get_actual")
                tasks[tag_id]= asyncio.create_task(
                        self._data_get_actual(
                            tag_params,
                            mes["data"]["start"],
                            mes["data"]["finish"],
                            mes["data"]["count"],
                            mes["data"]["value"]
                        )
                    )

            elif mes["data"]["timeStep"] is not None:
                self._logger.debug(f"Create task 'data_get_interpolated")
                tasks[tag_id]= asyncio.create_task(
                        self._data_get_interpolated(
                            tag_params,
                            mes["data"]["start"], mes["data"]["finish"],
                            mes["data"]["count"], mes["data"]["timeStep"]
                        )
                    )

            elif mes["data"]["start"] is None and \
                mes["data"]["count"] is None and \
                (mes["data"]["value"] is None or len(mes["data"]["value"]) == 0):
                self._logger.debug(f"Create task 'data_get_one")
                tasks[tag_id] = asyncio.create_task(
                        self._data_get_one(
                            tag_params,
                            mes["data"]["finish"]
                        )
                    )

            else:
                # Множество значений
                self._logger.debug(f"Create task 'data_get_many")

                tasks[tag_id]= asyncio.create_task(
                        self._data_get_many(
                            tag_params,
                            mes["data"]["start"],
                            mes["data"]["finish"],
                            mes["data"]["count"]
                        )
                    )

        result = {"data": []}

        if tasks:
            await asyncio.wait(list(tasks.values()))
        else:
            self._logger.debug(f"No data to return")
            return result

        for tag_id, task in tasks.items():
            tag_data = task.result()

            if not mes["data"]["actual"] and \
                (
                    mes["data"]["value"] is not None and \
                    len(mes["data"]["value"]) > 0
                ):
                tag_data = self._filter_data(
                    tag_data,
                    mes["data"]["value"],
                    self._tags[tag_id]['value_type'],
                    self._tags[tag_id]['step']
                )
                if mes["data"]["from_"] is None:
                    tag_data = [tag_data[-1]]

            excess = False
            if mes["data"]["maxCount"] is not None:
                excess = len(tag_data) > mes["data"]["maxCount"]

                if excess:
                    if mes["data"]["maxCount"] == 0:
                        tag_data = []
                    elif mes["data"]["maxCount"] == 1:
                        tag_data = tag_data[:1]
                    elif mes["data"]["maxCount"] == 2:
                        tag_data = [tag_data[0], tag_data[-1]]
                    else:
                        new_tag_data = tag_data[:mes["data"]["maxCount"] - 1]
                        new_tag_data.append(tag_data[-1])
                        tag_data = new_tag_data

            '''
            if mes["data"]["format"]:
                svc.format_data(tag_data, data.format)
            '''
            new_item = {
                "tagId": tag_id,
                "data": tag_data
            }
            if mes["data"]["maxCount"]:
                new_item["excess"] = excess
            result["data"].append(new_item)

        self._logger.debug(f"Data get result: {result}")

        return result

    def _filter_data(
            self, tag_data: List[tuple], value: List[Any], tag_type_code: int,
            tag_step: bool) -> List[tuple]:
        def estimate(x1: int, y1: int | float, x2: int, y2: int | float, y: int | float) -> int:
            '''
            Функция принимает на вход две точки прямой и значение, координату X которого возвращает.
            '''
            k = (y2 - y1)/(x2 - x1)
            b = y2 - k * x2

            x = round((y - b) / k)

            return x


        res = []
        if tag_step or tag_type_code not in [0, 1]:
            for item in tag_data:
                if tag_type_code == 4:
                    y = json.loads(item[0])
                else:
                    y = item[0]
                if y in value:
                    res.append(item)
        else:
            for i in range(1, len(tag_data)):
                y1 = tag_data[i - 1][0]
                y2 = tag_data[i][0]
                x1 = tag_data[i - 1][1]
                x2 = tag_data[i][1]
                if x1 == x2:
                    continue
                if y1 in value:
                    res.append(tag_data[i - 1])
                else:
                    if y1 is None or y2 is None:
                        continue
                    for val in value:
                        if val is None:
                            continue
                        if tag_type_code == 0 and isinstance(val, float):
                            continue
                        if ((y1 > val and y2 < val) or (y1 < val and y2 > val)):
                            x = estimate(x1, y1, x2, y2, val)
                            res.append((val, x, None))
            if tag_data[-1][0] in value:
                res.append(tag_data[-1])
        return res

    async def _data_get_interpolated(self,
                                     tag_cache: dict,
                                     start: int,
                                     finish: int,
                                     count: int,
                                     time_step: int) -> List[tuple]:
        """ Получение интерполированных значений с шагом time_step
        """
        tag_data = await self._data_get_many(tag_cache,
            start or (finish - time_step * (count - 1)),
            finish, None
        )
        # Создание ряда таймстэмпов с шагом `time_step`
        time_row = self._timestep_row(time_step, count, start, finish)

        if not tag_data:
            return [(None, x, None) for x in time_row]

        return self._interpolate(tag_data, time_row)

    def _interpolate(self, raw_data: List[tuple], time_row: List[int]) -> List[tuple]:
        """ Получение линейно интерполированных значений для ряда ``time_row`` по
        действительным значениям из БД (``raw_data``)

        :param raw_data: Реальные значения из БД
        :type raw_data: List[Dict]

        :param time_row: Временной ряд, для которого надо рассчитать значения
        :type time_row: List[int]

        :return:
        :rtype: List[Dict]
        """

        # Разбиение списка ``raw_data`` на подсписки по значению None
        # Если ``raw_data`` не имеет None, получается список [raw_data]
        none_indexes = [idx for idx, val in enumerate(raw_data) if val[0] is None]
        size = len(raw_data)
        if none_indexes:
            splitted_by_none = [raw_data[i: j+1] for i, j in
                zip([0] + none_indexes, none_indexes +
                ([size] if none_indexes[-1] != size else []))]
        else:
            splitted_by_none = [raw_data]

        data = []  # Результирующий список
        for period in splitted_by_none:
            if len(period) == 1:
                continue

            key_x = lambda d: d[1]
            min_ts = min(period, key=key_x)[1]
            max_ts = max(period, key=key_x)[1]
            is_last_period = period == splitted_by_none[-1]

            # В каждый подсписок добавляются значения из ряда ``time_row``
            period = [(None , ts, None) \
                      for ts in time_row if min_ts <= ts < max_ts] + period
            period.sort(key=key_x)

            if not is_last_period:
                period.pop()

            # Расширенный подсписок заворачивается в DataFrame и индексируется по 'x'
            df = pd.DataFrame(
                period,
                index=[r[1] for r in period]
            ).drop_duplicates(subset=1, keep='last')

            # линейная интерполяция значений 'y' в датафрейме для числовых тэгов
            # заполнение NaN полей ближайшими не-NaN для нечисловых тэгов
            df[[1, 0]] = df[[1, 0]].interpolate(
                method=('pad', 'index')[is_numeric_dtype(df[0])]
            )

            # None-значения 'q' заполняются ближайшим не-None значением сверху
            df[2].fillna(method='ffill', inplace=True)

            # Удаление из датафрейма всех элементов, чьи 'x' не принадлежат ``time_row``
            df = df.loc[df[1].isin(time_row)]
            df[[0, 2]] = df[[0, 2]].replace({np.nan: None})

            # Преобразование получившегося датафрейма и добавление значений к
            # результирующему списку
            data += list(df.to_dict('index').values())

        return data

    def _timestep_row(self,
                      time_step: int,
                      limit: int,
                      since: int,
                      till: int) -> List[int]:
        """ Возвращает временной ряд с шагом `time_step`

        :param time_step: Размер временного шага
        :type time_step: int
        :param limit: количество записей
        :type limit: int
        :param since: Точка начала отсчета
        :type since: int
        :param till: Точка окончания
        :type till: int

        :return: Ряд целых чисел длиной `limit` с шагом `time_step`
        :rtype: List[int]
        """

        if (since is None or till is None) and limit is None:
            raise AttributeError('Отсутствует параметр "count"')

        start_point = till
        time_step = -time_step
        if since is not None:
            start_point = since
            time_step = -time_step
            limit = min(
                int((till - since) / time_step) + 1,
                (limit, float('inf'))[limit is None]
            )

        row = []
        for i in range(0, limit):
            val = start_point + i * time_step
            if val < 0 or (till is not None and val > till):
                break
            row.append(val)

        if since is None:
            row.reverse()
        return row

    def _last_point(self, x: int, data: List[tuple]) -> Tuple[int, Any]:
        return (x, list(filter(lambda rec: rec[1] == x, data))[-1][0])

    async def _data_get_one(self,
                            tag_cache: dict,
                            finish: int) -> List[dict]:
        """ Получение значения на текущую метку времени
        """
        tag_data = await self._read_data(
            tag_cache=tag_cache, start=None, finish=finish, count=1,
            one_before=False, one_after=not tag_cache["step"], order=Order.CN_DESC
        )

        if not tag_data:
            if finish is not None:
                return [(None, finish, None)]

        x0 = tag_data[0][1]
        y0 = tag_data[0][0]
        try:
            x1, y1 = self._last_point(tag_data[1][1], tag_data)
            if not tag_cache["step"]:
                tag_data[0] = (
                    linear_interpolated(
                        (x0, y0), (x1, y1), finish
                    ), tag_data[0][1], tag_data[2]
                )

            # TODO: избавиться от этого try/except логикой приложения, т.к.
            # try/except отнимает слишком много времени

            tag_data.pop()

        except IndexError:
            # Если в выборке только одна запись и `to` меньше, чем `x` этой записи...
            if x0 > finish:
                tag_data[0] = (None, tag_data[0][1], None)
        finally:
            tag_data[0] = (tag_data[0][0], finish, tag_data[0][2])

        return tag_data

    async def _data_get_many(self,
                             tag_cache: dict,
                             start: int,
                             finish: int,
                             count: int = None) -> List[dict]:
        """ Получение значения на текущую метку времени
        """
        tag_data = await self._read_data(
            tag_cache, start, finish,
            (Order.CN_DESC if count is not None and start is None else Order.CN_ASC),
            count, True, True, None
        )
        if not tag_data:
            return []

        now_ms = t.ts()
        x0 = tag_data[0][1]
        y0 = tag_data[0][0]

        if start is not None:
            if x0 > start:
                # Если `from_` раньше времени первой записи в выборке
                tag_data.insert(0, (None, start, None))

            if len(tag_data) == 1:
                if x0 < start:
                    tag_data[0] = (tag_data[0][0], start, tag_data[0][2])
                    tag_data.append((y0, now_ms, tag_data[0][2]))
                return tag_data

            x1, y1 = self._last_point(tag_data[1][1], tag_data)
            if x1 == start:
                # Если время второй записи равно `from`,
                # то запись "перед from" не нужна
                tag_data.pop(0)

            if x0 < start < x1:
                tag_data[0] = (tag_data[0][0], start, tag_data[0][2])
                if tag_cache["step"]:
                    tag_data[0] = (y0, tag_data[0][1], tag_data[0][2])
                else:
                    tag_data[0] = (
                        linear_interpolated(
                            (x0, y0), (x1, y1), start
                        ), tag_data[0][1], tag_data[0][2]
                    )

        if finish is not None:
            # (xn; yn) - запись "после to"
            xn = tag_data[-1][1]
            yn = tag_data[-1][0]

            # (xn_1; yn_1) - запись перед значением `to`
            try:
                xn_1, yn_1 = self._last_point(tag_data[-2][1], tag_data)
            except IndexError:
                xn_1 = -1
                yn_1 = None

            if xn_1 == finish:
                # Если время предпоследней записи равно `to`,
                # то запись "после to" не нужна
                tag_data.pop()

            if xn_1 < finish < xn:
                if tag_cache["step"]:
                    y = yn_1
                else:
                    y = linear_interpolated(
                        (xn_1, yn_1), (xn, yn), finish
                    )
                tag_data[-1] = (
                    y, finish, tag_data[-2][2]
                )

            if finish > xn:
                tag_data.append((yn, finish, tag_data[-1][2]))

        if all((finish is None, now_ms > tag_data[-1][1])):
            tag_data.append((tag_data[-1][0], now_ms, tag_data[-1][2]))

        tag_data = self._limit_data(tag_data, count, start, finish)
        return tag_data

    async def _data_get_actual(self, tag_cache: dict, start: int, finish: int,
            count: int, value: Any = None):

        order = Order.CN_ASC
        if start is None:
            order = Order.CN_DESC
            count = (1, count)[bool(count)]

        raw_data = await self._read_data(
            tag_cache, start, finish, order, count, False, False, value
        )

        return raw_data

    async def _read_data(self, tag_cache: dict, start: int, finish: int,
        order: int, count: int, one_before: bool, one_after: bool, value: Any = None):

        #table = self._validate_container(table)
        conditions = ['TRUE']
        sql_select = f"SELECT id, x, y, q FROM \"{tag_cache['table']}\""

        if start is not None:
            conditions.append(f'x >= {start}')
        if finish is not None:
            conditions.append(f'x <= {finish}')

        value_filter, adapted_value = self._get_values_filter(value)

        queries = []
        if one_before and start:
            queries.append(f'({sql_select} WHERE x < {start} {value_filter} ORDER BY x DESC, id DESC LIMIT 1)')

        limit_str = ('', f'LIMIT {count}')[isinstance(count, int)]
        order = ('ASC', 'DESC')[order == Order.CN_DESC]
        conditions = ' AND '.join(conditions)

        queries.append(f'({sql_select} WHERE {conditions} {value_filter} ORDER BY x {order}, id DESC {limit_str})')

        if one_after and finish:
            queries.append(f'({sql_select} WHERE x > {finish} {value_filter} ORDER BY x ASC, id DESC LIMIT 1)')

        subquery = ' UNION '.join(queries)
        query_args = [f'SELECT x, y, q FROM ({subquery}) as sub ORDER BY sub.x ASC, id ASC']
        if adapted_value is not None:
            query_args += adapted_value

        records = []
        async with tag_cache["ds"].acquire() as conn:
            async with conn.transaction():
                async for r in conn.cursor(*query_args):
                    records.append((r.get('y'), r.get('x'), r.get('q')))
        return records

    def _get_values_filter(self, value: Any) -> tuple:
        """ Сериализация значения в SQL-фильтр

        :param value: Значение или массив значений
        :type value: Any

        :return: SQL-условие по полю `value`
        :rtype: Tuple[str, Any]
        """
        if value is None:
            return '', None

        adapted = []
        if isinstance(value, dict):
            condition = 'AND "y" @> $1'
            adapted.append(json.dumps(value))
        elif not isinstance(value, (list, tuple)):
            condition = 'AND "y" = $1'
            adapted.append(value)
        else:
            condition = 'AND (FALSE'
            if None in value:
                condition = f'{condition} OR "y" IS NULL'
                value = list(filter(lambda x: x is not None, value))
            if value:
                if isinstance(value[0], dict):
                    i = 1
                    for val in value:
                        condition = f'{condition} OR "y" @> ${i}'
                        adapted.append(json.dumps(val))
                        i += 1
                else:
                    condition = f'{condition} OR "y" = ANY($1)'
                    adapted.append(tuple(value))
            condition = f'{condition})'

        return condition, (None, adapted)[bool(adapted)]

    def _limit_data(self,
                    tag_data: List[dict],
                    count: int,
                    start: int,
                    finish: int):
        """ Ограничение количества записей в выборке.
        Если задан параметр ``since``, возвращается ``limit`` первых записей списка.
        Если ``since`` не задан (None), но задан ``till``, возвращается
        ``limit`` последних записей списка

        :param tag_data: исходная выборка, массив словарей {'x': int, 'y': Any, 'q': int}
        :type tag_data: List[Dict]

        :param limit: количество записей в выборке
        :type limit: int

        :param since: нижняя граница выборки
        :type since: int

        :param till: верхняя граница выборки
        :type till: int
        """
        if not count:
            return tag_data
        if start:
            return tag_data[:count]
        if finish:
            return tag_data[-count:]
        return tag_data

settings = DataStoragesAppPostgreSQLSettings()

app = DataStoragesAppPostgreSQL(settings=settings, title="DataStoragesAppPostgreSQL")
