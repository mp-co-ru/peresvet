import sys
import os
import json
import asyncio
import numbers
import copy
from abc import ABC, abstractmethod
from typing import Any, List, Tuple

import redis.asyncio as redis
import pandas as pd
from pandas.api.types import is_numeric_dtype
import numpy as np

sys.path.append(".")

from src.common import svc
from src.services.dataStorages.app.dataStorages_app_base_settings import DataStoragesAppBaseSettings

from src.common.hierarchy import (
    CN_SCOPE_BASE, CN_SCOPE_ONELEVEL, CN_SCOPE_SUBTREE
)
import src.common.times as t
from src.common.consts import (
    CNTagValueTypes as TVT,
    Order
)

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

class DataStoragesAppBase(svc.Svc, ABC):
    """Базовый класс для хранилищ данных.
    Реализует общую логику: работа с кэшем, поддержка нескольких экземпляров
    хранилища одного типа и т.д.

    Для работы данному классу требуется информация о тегах.
    Правильное поведение - запрос через брокер сообщений данных о теге, но
    пока сделаем, чтобы класс сам брал из иерархии нужные данные.

    Класс реализует кэш json-вида.

    "<service_name>:<tag_id1>": {
        "prsActive": true,
        "prsUpdate": true,
        "prsValueTypeCode": 1,
        "prsStep": false,
        "dss": {
            "dsId1": {}, # prsStore
            "dsId2": {}
        },
        "data": [(y, x, q)]
    }
    "<service_name>:<ds_id1>": {
        "prsActive": True,
        "tags": ["<tag_id1>", "<tag_id2>"]
    }

1) Кэш тегов строится по мере того, как происходит обращение
   записи/чтения к тегу
2) Кэш для баз данных вообще не строится
3) Каждый экземпляр сервиса создаёт свою уникальную очередь,
   которая подписывается на изменения поддерживаемых данным
   сервисом баз данных. В случае удаления базы не забываем эту убрать и
   подписку.
4) В случае создания новой базы её должен подхватить сервис, у которого
   не конкретизированы в конфигурации поддерживаемые им базы.
   Следствие: если у какого-то сервиса указана поддерживаемая им база(-ы),
   то у всех сервисов этого типа должны быть тоже указаны базы. Так как
   возможна ситуация:
   а) в модели две базы одного типа;
   б) есть два сервиса одного типа, у одного указана первая база, у второго
      ничего не указано, поэтому
   в) первый сервис поддерживает одну, указанную ему, базу, а второй - обе.
   В принципе, это не ошибка...
5) При выполнении команды linkTag кэш тега не строится для упрощения кода:
   кэш построится при первом обращении к тегу.
6) Данные кэша разделены на два ключа, чтобы можно было установить время
   жизни ключа "<service_name>:<tag_id1>". Ключ же "<service_name>" служит
   для хранения данных. Данные же будут удаляться при сбросе кэша в базу.
7) Сброс кэша в базу: сначала читаем список всех тегов базы из ldap, потом
   ищем данные уже в кэше.
8) UnlinkTag, тем не менее, удаляет ключ из "<service_name>:<dsId1>",
   предварительно сбросив кэш в базу.

    Args:
        settings (DataStoragesAppBaseSettings): Параметры конфигурации
    """

    def __init__(
            self, settings: DataStoragesAppBaseSettings, *args, **kwargs
        ):
        super().__init__(settings, *args, **kwargs)

        # словарь коннектов к хранилищам. имеет вид:
        # {
        #    "<ds_id>": <connection_pool>
        # }
        self._connection_pools = {}
        # коннект к кеш-серверу
        self._cache_pool = None

        # список id хранилищ, которые обслуживает сервис
        self._ds_ids = []

    def _set_handlers(self) -> dict:
        return {
            "tags.downloadData": self.tag_get,
            "tags.uploadData": self.tag_set,
            #"alerts.getAlarms": self._get_alarms,
            "alerts.alarmAcked": self.alarm_ack,
            "alerts.alarmOn": self.alarm_on,
            "alerts.alarmOff": self.alarm_off,
            "dataStorages.linkTag": self.link_tag,
            "dataStorages.unlinkTag": self.unlink_tag,
            "dataStorages.linkAlert": self.link_alert,
            "dataStorages.unlinkAlert": self.unlink_alert,
            "dataStorages.created": self.created,
            "dataStorages.updated": self.updated,
            "dataStorages.deleted": self.deleted
        }

    async def _bind_tag(self, tag_id: str, bind: bool) -> None:
        """
        Привязка тега для прослушивания.
        """
        self._logger.debug(f"Привязка: {bind} очереди для тега {tag_id}.")

        if bind:
            await self._amqp_consume_queue["queue"].bind(
                exchange=self._amqp_consume_queue["exchanges"]["tags"]["exchange"],
                routing_key=tag_id
            )
        else:
            await self._amqp_consume_queue["queue"].unbind(
                exchange=self._amqp_consume_queue["exchanges"]["tags"]["exchange"],
                routing_key=tag_id
            )

    async def _add_supported_ds(self, ds_id: str) -> None:
        """Метод добавляет в список поддерживаемых хранилищ новое.

        Args:
            ds_id (str): _description_
        """
        payload = {
            "id": [ds_id],
            "attributes": ["prsJsonConfigString", "prsActive"]
        }
        ds = await self._hierarchy.search(payload=payload)
        if ds[0][2]["prsActive"][0] == "TRUE":
            # если хранилище активно, то подсоединимся к нему
            connected = False
            while not connected:
                try:
                    self._connection_pools[ds_id] = await self._create_connection_pool(json.loads(ds[0][2]["prsJsonConfigString"][0]))
                    self._logger.info(f"Связь с базой данных {ds_id} установлена.")
                    connected = True
                except Exception as ex:
                    self._logger.error(f"Ошибка связи с базой данных '{ds_id}': {ex}")
                    await asyncio.sleep(5)

        # добавим в список поддерживаемых хранилищ новое
        self._ds_ids.append(ds_id)
        await self._amqp_consume_queue["queue"].bind(
            exchange=self._amqp_consume_queue["exchanges"]["main"]["exchange"],
            routing_key=ds_id
        )

        payload = {
            "base": ds_id,
            "filter": {
                "objectClass": ["prsDatastorageTagData"]
            },
            "attributes": ["cn"]
        }
        tags = await self._hierarchy.search(payload)
        tag_ids = [tag[2]["cn"][0] for tag in tags]

        # добавим ключ "svc_name:ds_id": {}
        await (self._cache.set(name=f"{self._config.svc_name}:{ds_id}",
                obj={
                    "prsActive": ds[0][2]["prsActive"][0] == "TRUE",
                    "tags": tag_ids
                }, nx=True)).exec()

        for tag_id in tag_ids:
            await self._bind_tag(tag_id, True)

    async def on_startup(self) -> None:

        await super().on_startup()

        try:
            self._cache_pool = redis.ConnectionPool.from_url(self._config.cache_url)

            payload = {}
            if self._config.datastorages_id:
                payload["id"] = self._config.datastorages_id
                # если указаны конкретные id хранилищ, которые надо обслуживать,
                # то отменяем базовую привязку очереди прослушивания
                await self._amqp_consume_queue["queue"].unbind(
                    exchange=self._amqp_consume_queue["exchanges"]["main"]["exchange"],
                    routing_key=self._config.consume["exchanges"]["main"]["routing_key"][0]
                )
            else:
                ds_node_id = await self._hierarchy.get_node_id("cn=dataStorages,cn=prs")
                payload = {
                    "base": ds_node_id,
                    "filter": {
                        "prsEntityTypeCode": [self._config.datastorage_type],
                        "objectClass": ["prsDataStorage"]
                    }
                }

            loop = asyncio.get_event_loop()
            dss = await self._hierarchy.search(payload=payload)
            for ds in dss:
                await self._add_supported_ds(ds[0])

            loop.call_later(self._config.cache_data_period, lambda: asyncio.create_task(self._write_cache_data()))

        except Exception as ex:
            self._logger.error(f"Ошибка инициализации хранилища: {ex}")

    async def created(self, mes: dict) -> None:
        # команда добавления новой базы данных
        # если в конфигурации сервиса указаны конкретные id баз для поддержки,
        # то эта ситуация отслеживается в методе _reject_message

        if self._config.datastorages_id:
            return
        
        await self._add_supported_ds(mes["data"]["id"])

    async def updated(self, mes: dict) -> None:
        # обновление атрибутов хранилища
        # привязка/отвязка тегов и тревог выполняется
        # методами link/unlink
        # необслуживаемые хранилища отсекаются методом reject_message
        ds_id = mes["data"]["id"]
        payload = {
            "id": mes["data"]["id"],
            "attributes": ["prsActive", "prsJsonConfigString"]
        }
        ds_data = await self._hierarchy.search(payload=payload)
        if not ds_data:
            self._logger.error(f"В модели нет данных по хранилищу {ds_id}")
            return

        self._connection_pools[ds_id] = None

        connected = False
        while not connected:
            try:
                self._connection_pools[ds_id] = await self._create_connection_pool(json.loads(ds_data[0][2]["prsJsonConfigString"][0]))
                self._logger.info(f"Связь с базой данных {ds_id} установлена.")
                connected = True
            except Exception as ex:
                self._logger.error(f"Ошибка связи с базой данных '{ds_id}': {ex}")
                await asyncio.sleep(5)

    async def deleted(self, mes: dict) -> None:
        # удаление хранилища
        ds_id = mes["data"]["id"]
        res = await self._cache.get(
            f"{self._config.svc_name}:{ds_id}", "tags"
        ).exec()

        self._cache.delete(f"{self._config.svc_name}:{ds_id}")

        for tag_id in res[0]:
            self._cache.delete(
                f"{self._config.svc_name}:{tag_id}",
                f"dss.{ds_id}"
            )
        await self._cache.exec()

    async def alarm_on(self, mes: dict) -> None:
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

        except Exception as ex:
            self._logger.error(f"Ошибка при записи данных тревоги {alert_id}: {ex}")

    async def alarm_ack(self, mes: dict) -> None:
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

        except Exception as ex:
            self._logger.error(f"Ошибка при записи данных тревоги {alert_id}: {ex}")

    async def alarm_off(self, mes: dict) -> None:
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

        except Exception as ex:
            self._logger.error(f"Ошибка при записи данных тревоги {alert_id}: {ex}")

    async def _reject_message(self, mes: dict) -> bool:

        # отсечём необрабатываемые сообщения:
        # если создано хранилище необслуживаемого типа
        if mes["action"] == "dataStorages.created":
            # если указан список поддерживаемых хранилищ
            if self._config.datastorages_id:
                return True

            payload = {
                "id": mes["data"]["id"],
                "attributes": ["prsEntityTypeCode"]
            }
            ds_res = await self._hierarchy.search(payload=payload)
            if not ds_res:
                self._logger.error(
                    f"В модели отсутствует хранилище {mes['data']['id']}"
                )
                return True

            if int(ds_res[0][2]["prsEntityTypCode"][0]) != \
                self._config.datastorage_type:
                return True

        # ...если приходят другие сообщения относительно необслуживаемых
        # хранилищ
        if mes["action"] in [
            "dataStorages.linkTag", "dataStorages.unlinkTag"
            "dataStorages.linkAlert", "dataStorages.unlinkAlert"
            ]:
            return not mes["data"]["dataStorageId"] in self._ds_ids

        if mes["action"] in [
            "dataStorages.updated",
            "dataStorages.deleted"
        ]:
            return not mes["data"]["id"] in self._ds_ids

        return False

    @abstractmethod
    async def _create_store_name_for_new_tag(self,
            ds_id: str, tag_id: str) -> dict | None:
        """Метод, создающий имя для нового места хранения данных тега.

        Args:
            ds_id (str): id хранилища
            tag_id (_type_): id тега

        Returns:
            dict: json с описанием хранилища тега
        """
        pass

    @abstractmethod
    async def _check_store_name_for_new_tag(self, ds_id: str, store: dict) -> bool:
        """Метод проверяет на корректность имя хранилища для нового тега,
        переданное клиентом.

        Args:
            store (dict): новое хранилище для тега

        Returns:
            bool: флаг корректности нового имени
        """
        pass

    @abstractmethod
    async def _create_store_for_tag(self, tag_id: str, ds_id: str, store: dict) -> None:
        pass

    async def link_tag(self, mes: dict) -> dict | None:
        """Метод привязки тега к хранилищу.
        В сообщении может приходить атрибут prsStore: пользователь знает,
        как организовать хранение данных для тега
        (как назвать метрику, таблицу и т.д.),
        иначе хранилище само организовывает место для хранения данных тега.

        Args:
            mes (dict): {
                "action": "dataStorages.linkTag",
                "data": {
                    "tagId": "tag_id",
                    "dataStorageId": "ds_id",
                    "attributes": {
                        "prsStore": {}
                    }
                }

        """

        tag_id = mes["data"]["tagId"]
        ds_id = mes["data"]["dataStorageId"]
        if ds_id not in self._ds_ids:
            self._logger.error(f"Хранилища {ds_id} нет в списке поддерживаемых.")
            return

        store = mes["data"]["attributes"].get("prsStore")
        if store is not None:
            check = await self._check_store_name_for_new_tag(ds_id=ds_id, store=store)
            if not check:
                self._logger.error(f"{store} не подходит для хранения данных тега {tag_id}")
                return {"prsStore": None}
        else:
            store = await self._create_store_name_for_new_tag(ds_id=ds_id, tag_id=tag_id)

        await self._create_store_for_tag(tag_id=tag_id, ds_id=ds_id, store=store)

        await self._bind_tag(tag_id, True)

        try:
            # добавим ключ "svc_name:ds_id": {}
            await self._cache.append(
                f"{self._config.svc_name}:{ds_id}",
                    "tags",
                    tag_id
            ).exec()            
        except Exception as ex:
            self._logger.error(f"Ошибка привязки тега {ex}")
            return {"prsStore": None}

        return {"prsStore": store}

    async def link_alert(self, mes: dict) -> dict:
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

    async def unlink_alert(self, mes: dict) -> None:
        """_summary_

        Args:
            mes (dict): {
                "action": "dataStorages.unlinkAlert",
                "data": {
                    "alertId": "alert_id"
                }
        """
        alert_params = self._alerts.get(mes["data"]["alertId"])
        if not alert_params:
            self._logger.warning(f"Тревога {mes['data']['alertId']} не привязана к хранилищу.")
            return

        async with alert_params["ds"].acquire() as conn:
            await conn.execute(
                f'drop table if exists "{alert_params["table"]}"'
            )

        self._alerts.pop(mes["data"]["alertId"])

        self._logger.info(f"Тревога {mes['data']['alertId']} отвязана от хранилища.")

    async def unlink_tag(self, mes: dict) -> None:
        """_summary_

        Args:
            mes (dict): {
                "action": "datastorages.unlinktag",
                "data": {
                    "tagId": "tag_id",
                    "dataStorageId": "ds_id"
                }
        """
        tag_id = mes["data"]["tagId"]
        ds_id = mes["data"]["dataStorageId"]
        try:
            # если есть кэш данных, то сначала сохраним его
            self._write_tag_data_to_db(tag_id)

            await self._cache.delete(
                f"{self._config.svc_name}:{tag_id}",
                f"dss.{ds_id}"
            ).exec()

            index = await self._cache.index(
                f"{self._config.svc_name}:{ds_id}", "tags", tag_id
            ).exec()
            if index[0] > -1:
                await self._cache.pop(
                    f"{self._config.svc_name}:{ds_id}", "tags", index[0]
                ).exec()
            
            self._bind_tag(tag_id, False)
        except Exception as ex:
            self._logger.error(f"Ошибка отвязки тега: {ex}")

        self._logger.info(f"Тег {tag_id} отвязан от хранилища.")

    @abstractmethod
    async def _write_tag_data_to_db(
            self, tag_id: str) -> None:

        # метод, переопределяемый в классах-потомках
        # записывает данные одного тега в хранилище
        pass

    async def _write_cache_data(self, tag_ids: list[str] = None) -> None:
        """Функция сбрасывает кэш данных тегов в базу для поддерживаемых
        баз данных если tag_ids - пустой список, то сбрасываются
        все теги из кэша иначе - только те, которые в списке.

        При сбросе кэша не проверяется активность/неактивность ни тегов, ни
        хранилищ: сам вызов этой функции может инициироваться переводом
        тега или хранилища в неактивное состояние.

        Args:
            tag_ids (str], optional): список тегов.
        """

        self._logger.info("Запись кэша данных в хранилища...")
        scheduled = False
        try:
            
            if not tag_ids:
                # если пустой список тегов, это значит, что сбрасывается весь кэш,
                # то есть происходит запуск процедуры по расписанию
                scheduled = True
                tag_ids = set()
                for ds_id in self._ds_ids:
                    # определим, активна ли база
                    res = await self._cache.get(
                        f"{self._config.svc_name}:{ds_id}", "prsActive", "tags"
                    ).exec()
                    if res[0] is None:
                        self._logger.warning(f"Нет кэша для хранилища {ds_id}")
                        continue
                    if not res[0]["prsActive"]:
                        self._logger.info(
                            f"Хранилище {ds_id} неактивно."
                        )
                        continue
                    tag_ids = tag_ids.union(set(res[0]["tags"]))

            for tag_id in tag_ids:
                res = await self._cache.get(
                    f"{self._config.svc_name}:{tag_id}",
                    f"prsActive"
                ).exec()
                if res[0] is None:
                    # если нет кэша у тега
                    if not await self._create_tag_cache(tag_id):
                        index = await self._cache.index(
                            f"{self._config.svc_name}:{ds_id}", "tags", tag_id
                        ).exec()

                        if index[0] > -1:
                            await self._cache.pop(
                                f"{self._config.svc_name}:{ds_id}", "tags", index[0]
                            ).exec()
                else:
                    await self._write_tag_data_to_db(tag_id)

        except Exception as ex:
            self._logger.error(f"Ошибка записи данных в базу: {ex}")
        
        loop = asyncio.get_event_loop()

        if scheduled:
            loop.call_later(self._config.cache_data_period, lambda: asyncio.create_task(self._write_cache_data()))

    async def tag_set(self, mes: dict) -> None:
        """

        Args:
            mes (dict): {
                "action": "tags.uploadData",
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
        try:
            self._logger.info(f"{self._config.svc_name}: tag set: {mes}")

            for tag_data in mes["data"]["data"]:
                tag_id = tag_data["tagId"]

                # проверим, активен ли тег и активны ли хранилища
                res = await self._cache.get(
                    f"{self._config.svc_name}:{tag_id}"
                ).exec()

                if res[0] is None:
                    # если нет кэша у тега
                    cache = await self._create_tag_cache(tag_id)
                else:
                    cache = res[0]
                if not cache["prsActive"]:
                    self._logger.info(f"Тег {tag_id} неактивен, данные не записываются.")
                else:
                    await self._cache.append(
                        f"{self._config.svc_name}:{tag_id}",
                        f"$.data", *tag_data["data"]
                    ).exec()
                    self._logger.info(f"Кэш тега {tag_id} обновлён.")

        except Exception as ex:
            self._logger.error(f"Ошибка обновления данных в кэше: {ex}")
        
    async def _create_tag_cache(self, tag_id: str) -> dict | bool | None:
        """Функция подготовки кэша с данными о теге.

        Возвращаем всегда сформированный кэш целиком, независимо от того, был
        тег в кэше или ещё нет.

        Кэш для тега всегда строится на основании данных из иерархии. Текущие
        данные в кэше не учитываются, это повышает достоверность данных в кэше.

        Формат кэша:
        {
            "prsActive": true,
            "prsUpdate": true,
            "prsValueTypeCode": 1,
            "prsStep": false,
            "dss": {
                "dsId1": {}, # prsStore
                "dsId2": {}
            },
            "data": [(y, x, q)]
        }

        Args:
            ds_id (str): id хранилища (тег может быть привязан
                к нескольким хранилищам, для каждого - свой prsStore)
            tag_id (str): id тега, для которого формируем кэш
            ds_id (str): id хранилища

        Returns:
            dict | None: сформированный кэш тега
        """

        # получим атрибуты тега ---------------------------
        payload = {
            "id": tag_id,
            "attributes": [
                "prsActive",
                "prsUpdate",
                "prsValueTypeCode",
                "prsStep"
            ]
        }
        res = await self._hierarchy.search(payload=payload)
        if not res:
            return False
        tag_attrs = res[0][2]
        # ------------------------------------------------

        # подготовим первоначальный кэш тега из атрибутов ---
        tag_cache = {
            "prsActive": tag_attrs["prsActive"][0] == "TRUE",
            "prsUpdate": tag_attrs["prsUpdate"][0] == "TRUE",
            "prsValueTypeCode": int(tag_attrs["prsValueTypeCode"][0]),
            "prsStep": tag_attrs["prsStep"][0] == "TRUE",
            "dss": {},
            "data": []
        }

        # попробуем найти привязку тега к хранилищу ------------
        for ds_id in self._ds_ids:
            payload = {
                "base": ds_id,
                "scope": CN_SCOPE_SUBTREE,
                "filter": {
                    "cn": [tag_id],
                    "objectClass": ["prsDatastorageTagData"]
                },
                "deref": False,
                "attributes": ["prsStore"]
            }
            res = await self._hierarchy.search(payload=payload)
            if res:
                tag_cache["dss"][ds_id] = json.loads(res[0][2]["prsStore"][0])
        # ------------------------------------------------------------

        try:
            await self._cache.set(
                name=f"{self._config.svc_name}:{tag_id}", obj=tag_cache, nx=True
            ).exec()
        except Exception as ex:
            self._logger.error(ex)

        return tag_cache

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

    async def _create_connection_pool(self, config: dict) -> Any:
        """Метод создаёт пул коннектов к базе.
        Конфигурация базы передаётся в словаре config.
        Каждый класс для специфического хранилища переопределяет этот метод

        Args:
            config (dict): _description_
        """
        pass

    def _key_for_ds(self, ds_id: str) -> str:
        """Метод возвращает имя ключа кэша для хранилища.

        Args:
            ds_id (str): id хранилища

        Returns:
            str: имя ключа
        """
        return f"{self._config.svc_name} {ds_id}"

    async def tag_get(self, mes: dict) -> dict:
        """_summary_

        Args:
            mes (dict): {
                "action": "tags.downloadData",
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

        # TODO: разобраться, как читать данные, если тег привязан к разным хранилищам

        self._logger.debug(f"Чтение данных: {mes}")

        tasks = {}

        await self._write_cache_data(mes["data"]["tagId"])

        for tag_id in mes["data"]["tagId"]:
            # Если ключ actual установлен в true, ключ timeStep не учитывается
            if mes["data"]["actual"] or (mes["data"]["value"] is not None \
            and len(mes["data"]["value"]) > 0):
                mes["data"]["timeStep"] = None

            if mes["data"]["actual"]:
                tasks[tag_id]= asyncio.create_task(
                        self._data_get_actual(
                            tag_id,
                            mes["data"]["start"],
                            mes["data"]["finish"],
                            mes["data"]["count"],
                            mes["data"]["value"]
                        )
                    )

            elif mes["data"]["timeStep"] is not None:
                tasks[tag_id]= asyncio.create_task(
                        self._data_get_interpolated(
                            tag_id,
                            mes["data"]["start"], mes["data"]["finish"],
                            mes["data"]["count"], mes["data"]["timeStep"]
                        )
                    )

            elif mes["data"]["start"] is None and \
                mes["data"]["count"] is None and \
                (mes["data"]["value"] is None or len(mes["data"]["value"]) == 0):
                tasks[tag_id] = asyncio.create_task(
                        self._data_get_one(
                            tag_id,
                            mes["data"]["finish"]
                        )
                    )

            else:
                # Множество значений
                tasks[tag_id]= asyncio.create_task(
                        self._data_get_many(
                            tag_id,
                            mes["data"]["start"],
                            mes["data"]["finish"],
                            mes["data"]["count"]
                        )
                    )

            result = {"data": []}

            if tasks:
                await asyncio.wait(list(tasks.values()))
            else:
                self._logger.debug(f"Нет возвращаемых данных.")
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

            self._logger.debug(f"Получение данных: {result}")

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
                                     tag_id: str,
                                     start: int,
                                     finish: int,
                                     count: int,
                                     time_step: int) -> List[tuple]:
        """ Получение интерполированных значений с шагом time_step
        """
        tag_data = await self._data_get_many(tag_id,
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
        действительным значениям из БД (``raw_data``\)

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
                            tag_id: str,
                            finish: int) -> List[dict]:
        """ Получение значения на текущую метку времени
        """
        tag_cache = await self._cache.get(
            f"{self._config.svc_name}:{tag_id}", "prsStep", "prsValueTypeCode"
        ).exec()
        if tag_cache[0] is None:
            self._logger.error(f"Тег {tag_id} отсутствует в кэше.")
            return []
        step = tag_cache[0]["prsStep"]
        value_type_code = tag_cache[0]["prsValueTypeCode"]
        
        tag_data = await self._read_data(
            tag_id=tag_id, start=None, finish=finish, count=1,
            one_before=False, one_after=not step, order=Order.CN_DESC
        )

        if not tag_data:
            if finish is not None:
                return [(None, finish, None)]

        x0 = tag_data[0][1]
        y0 = tag_data[0][0]
        try:
            x1, y1 = self._last_point(tag_data[1][1], tag_data)
            if not step:
                y = linear_interpolated(
                        (x0, y0), (x1, y1), finish
                    )
                if value_type_code == 0:
                    y = round(y)
                tag_data[0] = (y, tag_data[0][1], tag_data[0][2])

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
                             tag_id: str,
                             start: int,
                             finish: int,
                             count: int = None) -> List[dict]:

        tag_cache = await self._cache.get(
            f"{self._config.svc_name}:{tag_id}", "prsStep"
        ).exec()
        if tag_cache[0] is None:
            self._logger.error(f"Тег {tag_id} отсутствует в кэше.")
            return []
        step = tag_cache[0]
        
        tag_data = await self._read_data(
            tag_id, start, finish,
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
                if step:
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
                if step:
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

    async def _data_get_actual(self, tag_id: str, start: int, finish: int,
            count: int, value: Any = None):

        order = Order.CN_ASC
        if start is None:
            order = Order.CN_DESC
            count = (1, count)[bool(count)]

        raw_data = await self._read_data(
            tag_id, start, finish, order, count, False, False, value
        )

        return raw_data

    @abstractmethod
    async def _read_data(self, tag_id: str, start: int, finish: int,
        order: int, count: int, one_before: bool, one_after: bool, value: Any = None):

        pass

    def _limit_data(self,
                    tag_data: List[dict],
                    count: int,
                    start: int,
                    finish: int):
        """ Ограничение количества записей в выборке.
        Если задан параметр ``since``\, возвращается ``limit`` первых записей списка.
        Если ``since`` не задан (None), но задан ``till``\, возвращается
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
