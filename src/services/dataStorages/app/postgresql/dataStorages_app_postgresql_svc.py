import sys
import json
import numbers
import copy
from typing import Any, List, Tuple

import redis.asyncio as redis

try:
    import uvicorn
except ModuleNotFoundError as _:
    pass

sys.path.append(".")

from src.services.dataStorages.app.postgresql.dataStorages_app_postgresql_settings import DataStoragesAppPostgreSQLSettings
from src.services.dataStorages.app.dataStorages_app_base import DataStoragesAppBase
import src.common.times as t
from src.common.consts import (
    CNTagValueTypes as TVT,
    Order
)

import asyncpg as apg
from asyncpg.exceptions import PostgresError

class DataStoragesAppPostgreSQL(DataStoragesAppBase):

    def __init__(
            self, settings: DataStoragesAppPostgreSQLSettings, *args, **kwargs
        ):

        super().__init__(settings, *args, **kwargs)

    async def _create_store_name_for_new_tag(self,
            ds_id: str, tag_id: str) -> dict | None:
        """Метод, создающий имя для нового места хранения данных тега.

        Args:
            ds_id (str): id хранилища
            tag_id (_type_): id тега

        Returns:
            dict: json с описанием хранилища тега
        """
        return {
            "table": f"t_{tag_id}"
        }

    async def _check_store_name_for_new_tag(self, store: dict) -> bool:
        """Метод проверяет на корректность имя хранилища для нового тега,
        переданное клиентом.

        Args:
            store (dict): новое хранилище для тега

        Returns:
            bool: флаг корректности нового имени
        """
        return bool(store.get("table"))

    async def _drop_store_for_tag(self, tag_id: str, ds_id: str) -> None:
        payload = {
            "base": ds_id,
            "filter": {
                "objectClass": ["prsDatastorageTagData"],
                "cn": [tag_id]
            },
            "attributes": ["prsStore"]
        }
        tag_data = await self._hierarchy.search(payload=payload)
        if tag_data:
            async with self._connection_pools[ds_id].acquire() as conn:
                tbl_name = json.loads(tag_data[0][2]["prsStore"][0])["table"]
                await conn.execute(
                    f'drop table if exists "{tbl_name}"'
                )
                self._logger.info(f"{self._config.svc_name} :: Хранилище тега '{tag_id}' в '{ds_id}' удалено.")

    async def _drop_store_for_alert(self, alert_id: str, ds_id: str) -> None:
        payload = {
            "base": ds_id,
            "filter": {
                "objectClass": ["prsDatastorageAlertData"],
                "cn": [alert_id]
            },
            "attributes": ["prsStore"]
        }
        alert_data = await self._hierarchy.search(payload=payload)
        if alert_data:        
            async with self._connection_pools[ds_id].acquire() as conn:
                tbl_name = json.loads(alert_data[0][2]["prsStore"][0])["table"]
                await conn.execute(
                    f'drop table if exists "{tbl_name}"'
                )
                self._logger.info(f"{self._config.svc_name} :: Хранилище тревоги '{alert_id}' в '{ds_id}' удалено.")
    
    async def _create_store_for_tag(self, tag_id: str, ds_id: str, store: dict) -> None:
        try:
            async with self._connection_pools[ds_id].acquire() as conn:
                tbl_name = store["table"]
                await conn.execute(
                    f'drop table if exists "{tbl_name}"'
                )

                payload = {
                    "id": tag_id,
                    "attributes": ["prsValueTypeCode"]
                }
                res = await self._hierarchy.search(payload=payload)
                if not res:
                    self._logger.error(f"{self._config.svc_name} :: Нет данных по тегу {tag_id}")
                    return

                value_type = int(res[0][2]["prsValueTypeCode"][0])

                match value_type:
                    case TVT.CN_INT:
                        s_type = "bigint"
                    case TVT.CN_DOUBLE:
                        s_type = "double precision"
                    case TVT.CN_STR:
                        s_type = "text"
                    case TVT.CN_JSON:
                        s_type = "jsonb"
                    case _:
                        er_str = f"Тег: {tag_id}; неизвестный тип данных: {value_type}"
                        self._logger.error(f"{self._config.svc_name} :: {er_str}")
                        return

                query = (f'CREATE TABLE public."{tbl_name}" ('
                        f'"id" serial primary key,'
                        f'"x" bigint NOT NULL,'
                        f'"y" {s_type},'
                        f'"q" int);'
                        # Создание индекса на поле "метка времени" ("ts")
                        f'CREATE INDEX "{tbl_name}_idx" ON public."{tbl_name}" '
                        f'USING btree ("x");')

                if value_type == 4:
                    query += (f'CREATE INDEX "{tbl_name}_json__idx" ON public."{tbl_name}" '
                                'USING gin ("y" jsonb_path_ops);')

                await conn.execute(query)

        except Exception as ex:
            self._logger.error(f"{self._config.svc_name} :: Ошибка создания хранилища тега: {ex}")

    async def _create_store_name_for_new_alert(self,
            ds_id: str, alert_id: str) -> dict | None:
        """Метод, создающий имя для нового места хранения данных тега.

        Args:
            ds_id (str): id хранилища
            alert_id (_type_): id тревоги

        Returns:
            dict: json с описанием хранилища тега
        """
        return {
            "table": f"a_{alert_id}"
        }

    async def _check_store_name_for_new_tag(self, store: dict) -> bool:
        """Метод проверяет на корректность имя хранилища для новой тревоги,
        переданное клиентом.

        Args:
            store (dict): новое хранилище для тревоги

        Returns:
            bool: флаг корректности нового имени
        """
        return bool(store.get("table"))

    async def _create_store_for_alert(self, alert_id: str, ds_id: str, store: dict) -> None:
        
        try:
            async with self._connection_pools[ds_id].acquire() as conn:
                tbl_name = store["table"]
                await conn.execute(
                    f'drop table if exists "{tbl_name}"'
                )

                query = (f'CREATE TABLE public."{tbl_name}" ('
                    f'"id" serial primary key,'
                    f'"x" bigint NOT NULL,' # время возникновения тревоги
                    f'"cx" bigint,'         # время квитирования
                    f'"e" bigint);'         # время пропадания тревоги
                    # Создание индекса на поле "метка времени" ("x")
                    f'CREATE INDEX "{tbl_name}_idx" ON public."{tbl_name}" '
                    f'USING btree ("x");')

                await conn.execute(query)

        except Exception as ex:
            self._logger.error(f"{self._config.svc_name} :: Ошибка создания хранилища тега: {ex}")

    async def _alarm_on(self, mes: dict, routing_key: str = None) -> None:

        self._logger.debug(f"Обработка возникновения тревоги: {mes}")

        alert_id = mes["alertId"]

        alert_params = await self._cache.get(f"{alert_id}.{self._config.svc_name}").exec()
        if not alert_params[0]:
            await self._create_alert_cache(alert_id)
            alert_params = await self._cache.get(f"{alert_id}.{self._config.svc_name}").exec()
            if not alert_params[0]:
                self._logger.error(f"{self._config.svc_name} :: Ошибка построения кэша тревоги {alert_id}")
                return

        alert_params = alert_params[0]
        for ds_id, prsStore in alert_params["dss"].items():
            connection_pool = self._connection_pools.get(ds_id)
            if connection_pool is None:
                continue

            alert_tbl = prsStore["table"]

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
                                records=[(mes["x"], None, None)],
                                columns=('x', 'cx', 'e'))

                            self._logger.debug(f"Тревога {alert_id} зафиксирована.")
                        else:
                            self._logger.debug(f"Тревога {alert_id} уже активна.")

            except PostgresError as ex:
                self._logger.error(f"{self._config.svc_name} :: Ошибка при записи данных тревоги {alert_id}: {ex}")

    async def _alarm_ack(self, mes: dict, routing_key: str = None) -> None:

        self._logger.debug(f"Обработка квитирования тревоги: {mes}")

        alert_id = mes["alertId"]
        alert_params = await self._cache.get(f"{alert_id}.{self._config.svc_name}").exec()
        if not alert_params[0]:
            await self._create_alert_cache(alert_id)
            alert_params = await self._cache.get(f"{alert_id}.{self._config.svc_name}").exec()
            if not alert_params[0]:
                self._logger.error(f"{self._config.svc_name} :: Ошибка построения кэша тревоги {alert_id}")
                return

        alert_params = alert_params[0]
        for ds_id, prsStore in alert_params["dss"].items():
            connection_pool = self._connection_pools.get(ds_id)
            if connection_pool is None:
                continue

            alert_tbl = prsStore["table"]

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

                        q = f"update \"{alert_tbl}\" set cx = {mes['x']}"
                        await conn.execute(q)

                        self._logger.debug(f"Тревога {alert_id} квитирована.")

            except PostgresError as ex:
                self._logger.error(f"{self._config.svc_name} :: Ошибка при записи данных тревоги {alert_id}: {ex}")

    async def _alarm_off(self, mes: dict, routing_key: str = None) -> None:
        """Факт пропадания тревоги.

        Args:
            mes (dict): {"alertId": "alert_id", "x": 123}

        """
        self._logger.debug(f"Обработка пропадания тревоги: {mes}")
        alert_id = mes["alertId"]

        alert_params = await self._cache.get(f"{alert_id}.{self._config.svc_name}")
        if not alert_params:
            alert_params = await self._create_alert_cache(alert_id)
            if not alert_params:
                self._logger.error(f"{self._config.svc_name} :: Ошибка построения кэша тревоги {alert_id}")
                return

        for ds_id, prsStore in alert_params["dss"].items():
            connection_pool = self._connection_pools.get(ds_id)
            if connection_pool is None:
                continue

            alert_tbl = prsStore["table"]

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

                        self._logger.debug(f"Тревога {alert_id} закончена.")

            except PostgresError as ex:
                self._logger.error(f"{self._config.svc_name} :: Ошибка при записи данных тревоги {alert_id}: {ex}")

    async def _tag_updated(self, mes: dict, routing_key: str = None):
        tag_id = mes['id']
        
        payload = {
            "id": tag_id,
            "attributes": ["prsValueTypeCode"]
        }
        tag_data = await self._hierarchy.search(payload=payload)
        if not tag_data:
            self._logger.error(f"{self._config.svc_name} :: В модели нет данных по тегу {tag_id}")
            return
        new_type = int(tag_data[0][2]["prsValueTypeCode"][0])

        # тег может быть привязан к нескольким хранилищам
        for ds_id in self._connection_pools.keys():
            payload = {
                "base": ds_id,
                "filter": {"cn": [tag_id], "objectClass": ["prsDatastorageTagData"]},
                "deref": False,
                "attributes": ["prsJsonConfigString", "prsStore"]
            }
            tag_link_data = await self._hierarchy.search(payload=payload)
            if not tag_link_data:
                self._logger.error(f"{self._config.svc_name} :: Тег '{tag_id}' не привязан к хранилищу '{ds_id}'")
                continue
            try:
                old_type = int(json.loads(tag_link_data[0][2]["prsJsonConfigString"][0])["prsValueTypeCode"])
            except:
                self._logger.error(f"{self._config.svc_name} :: Ошибка определения старого типа данных для тега '{tag_id}', хранилище '{ds_id}'.")
                continue

            if new_type != old_type:
                store = json.loads(tag_link_data[0][2]["prsStore"][0])
                await self._create_store_for_tag(tag_id=tag_id, ds_id=ds_id, store=store)
                await self._hierarchy.modify(
                    tag_link_data[0][0], 
                    {
                        "prsJsonConfigString": {"prsValueTypeCode": new_type}
                    }
                )
                
                self._logger.info(f"{self._config.svc_name} :: Хранилище тега '{tag_id}' в '{ds_id}' изменено.")        

        await self._delete_tag_cache(tag_id)
        await self._create_tag_cache(tag_id)

    async def _alert_deleted(self, mes: dict, routing_key: str = None):
        alert_id = mes['id']
        
        for ds_id in self._connection_pools.keys():
            await self._drop_store_for_alert(alert_id, ds_id)

        await super()._alert_deleted(mes, routing_key)

    async def _tag_deleted(self, mes: dict, routing_key: str = None):
        tag_id = mes['id']
        
        for ds_id in self._connection_pools.keys():
            await self._drop_store_for_tag(tag_id, ds_id)

        await super()._tag_deleted(mes, routing_key)

    async def _reject_message(self, mes: dict) -> bool:
        return False

    async def _write_tag_data_to_db(
            self, tag_id: str) -> None :

        # метод, переопределяемый в классах-потомках
        # записывает данные одного тега в хранилище
        self._logger.debug(f"Запись данных тега '{tag_id}' из кэша в хранилища...")

        try:
            tag_cache = await self._cache.get(
                f"{tag_id}.{self._config.svc_name}", "$"
            ).set(
                f"{tag_id}.{self._config.svc_name}", "$.data", []
            ).exec()

            if not tag_cache[0][0]["data"]:
                self._logger.debug(f"Кэш данных тега {tag_id} пустой.")
                return

            for ds_id in tag_cache[0][0]["dss"].keys():
                active = await self._cache.get(
                    f"{ds_id}.{self._config.svc_name}", "prsActive"
                ).exec()
                if active[0] is None:
                    self._logger.error(
                        f"{self._config.svc_name} :: Несоответствие кэша тега {tag_id} c кэшем хранилища {ds_id}")
                    continue

                # если хранилище неактивно, данные в него не записываем
                if not active[0]:
                    self._logger.error(
                        f"{self._config.svc_name} :: Хранилище {ds_id} неактивно.")
                    continue

                async with self._connection_pools[ds_id].acquire() as conn:
                    tag_tbl = tag_cache[0][0]["dss"][ds_id]["table"]

                    data = tag_cache[0][0]["data"]
                    async with conn.transaction(isolation='read_committed'):
                        if tag_cache[0][0]["prsUpdate"]:
                            xs = [str(x) for _, x, _ in data]
                            q = f'delete from "{tag_tbl}" where x in ({",".join(xs)}); '
                            await conn.execute(q)
                        if tag_cache[0][0]["prsValueTypeCode"] == 4:
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

        except Exception as ex:
            self._logger.error(f"{self._config.svc_name} :: Ошибка записи данных в базу {ds_id}: {ex}")

    async def _prepare_alert_data(self, alert_id: str, ds_id: str) -> dict | None:
        get_alert_data = {
            "id": [alert_id],
            "attributes": [
                "prsActive"
            ]
        }

        alert_data = await self._hierarchy.search(payload=get_alert_data)

        if not alert_data:
            self._logger.info(f"{self._config.svc_name} :: Не найдена тревога {alert_id}")
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
        Для PostgreSQL в словаре конфигурации только один ключ - dsn.

        Args:
            config (dict): _description_
        """
        return await apg.create_pool(dsn=config["dsn"])

    async def _unlink_alert(self, mes: dict, routing_key: str = None) -> None:
        """_summary_

        Args:
            mes (dict): {
                "alertId": "alert_id",
                "dataStorageId: ds_id"
            }

        """
        alert_id = mes["alertId"]
        ds_id = mes["dataStorageId"]
        
        payload = {
            "base": ds_id,
            "filter": {
                "objectClass": ["prsDatastorageAlertData"],
                "cn": [alert_id]
            },
            "attributes": ["prsStore"]
        }
        res = await self._hierarchy.search(payload=payload)
        if not res:
            self._logger.error(f"{self._config.svc_name} :: Тревога {alert_id} не привязана к хранилищу {ds_id}")
            return

        table_name = json.loads(res[0][2]["prsStore"][0])["table"]
        async with self._connection_pools[ds_id].acquire() as conn:
            await conn.execute(
                f'drop table if exists "{table_name}"'
            )

        await self._bind_alert(alert_id, False)
        index = await self._cache.index(f"{ds_id}.{self._config.svc_name}", "alerts", alert_id).exec()
        await self._cache.pop(f"{ds_id}.{self._config.svc_name}", "alerts", index).exec()

        self._logger.info(f"{self._config.svc_name} :: Тревога {alert_id} отвязана от хранилища {ds_id}.")

    async def _unlink_tag(self, mes: dict, routing_key: str = None) -> None:
        """_summary_

        Args:
            mes (dict): {
                "action": "datastorages.unlinktag",
                "data": {
                    "tagId": "tag_id",
                    "dataStorageId": "ds_id"
                }
        """
        tag_id = mes["tagId"]
        ds_id = mes["dataStorageId"]
        
        payload = {
            "base": ds_id,
            "filter": {
                "objectClass": ["prsDatastorageAlertData"],
                "cn": [tag_id]
            },
            "attributes": ["prsStore"]
        }
        res = await self._hierarchy.search(payload=payload)
        if not res:
            self._logger.error(f"{self._config.svc_name} :: Тег {tag_id} не привязан к хранилищу {ds_id}")
            return

        table_name = json.loads(res[0][2]["prsStore"][0])["table"]
        async with self._connection_pools[ds_id].acquire() as conn:
            await conn.execute(
                f'drop table if exists "{table_name}"'
            )

        await self._bind_tag(tag_id, False)
        index = await self._cache.index(f"{ds_id}.{self._config.svc_name}", "tags", tag_id).exec()
        await self._cache.pop(f"{ds_id}.{self._config.svc_name}", "tags", index).exec()

        self._logger.info(f"{self._config.svc_name} :: Тег {tag_id} отвязан от хранилища {ds_id}.")

    async def _read_data(self, tag_id: str, start: int, finish: int,
        order: int, count: int, one_before: bool, one_after: bool, value: Any = None):

        actual_ds = None
        tag_data = await self._cache.get(
            f"{tag_id}.{self._config.svc_name}",
            "prsActive", "dss", "prsValueTypeCode"
        ).exec()

        if not tag_data[0]:
            self._logger.error(f"{self._config.svc_name} :: Тег {tag_id} отсутствует в кэше.")
            
            return []
        if not tag_data[0]["prsActive"]:
            self._logger.error(f"{self._config.svc_name} :: Тег {tag_id} неактивен.")
            
            return []

        # если тег привязан к нескольким хранилищам, пока непонятна логика
        # из какого хранилища брать данные.
        # пока будем брать из первого активного
        for ds_id in tag_data[0]["dss"].keys():
            ds_res = await self._cache.get(
                f"{ds_id}.{self._config.svc_name}",
                "prsActive"
            ).exec()
            if ds_res[0] is None:
                self._logger.error(
                    f"{self._config.svc_name} :: Хранилище {ds_id} отсутствует в кэше."
                )
            if ds_res[0]:
                actual_ds = ds_id
                break
        
        if not actual_ds:
            self._logger.error(
                f"{self._config.svc_name} :: Не найдено актуальное хранилище для тега {tag_id}"
            )
            return []

        conditions = ['TRUE']
        sql_select = f"SELECT id, x, y, q FROM \"{tag_data[0]['dss'][actual_ds]['table']}\""

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
        async with self._connection_pools[actual_ds].acquire() as conn:
            async with conn.transaction():
                async for r in conn.cursor(*query_args):
                    val = r.get('y')
                    if tag_data[0]["prsValueTypeCode"] == 4:
                        val = json.loads(val)
                    records.append((val, r.get('x'), r.get('q')))
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

settings = DataStoragesAppPostgreSQLSettings()

app = DataStoragesAppPostgreSQL(settings=settings, title="DataStoragesAppPostgreSQL")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
