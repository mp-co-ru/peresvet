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

class DataStoragesAppPostgreSQL(DataStoragesAppBase):

    def __init__(
            self, settings: DataStoragesAppPostgreSQLSettings, *args, **kwargs
        ):

        super().__init__(settings, *args, **kwargs)

        self._tags = {}
        self._alerts = {}
        self._data_cache = {}

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
                    self._logger.error(f"Нет данных по тегу {tag_id}")
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
                        self._logger.error(er_str)
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
            self._logger.error(f"Ошибка обновления данных в кэше: {ex}")

    async def alarm_on(self, mes: dict) -> None:

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

    async def alarm_ack(self, mes: dict) -> None:

        self._logger.debug(f"Обработка квитирования тревоги: {mes}")

        alert_id = mes["data"]["alertId"]
        alert_params = self._alerts.get(alert_id)
        if not alert_params:
            self._logger.error(f"Тревога {alert_id} не привязана к хранилищу.")
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

    async def alarm_off(self, mes: dict) -> None:
        """Факт пропадания тревоги.

        Args:
            mes (dict): {"action": "alerts.alrmOff", "data": {"alertId": "alert_id", "x": 123}}

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

    async def link_alert(self, mes: dict) -> dict:

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
        tag_id = mes["data"]["tagId"]
        try:
            client = redis.Redis(connection_pool=self._cache_pool)

            async with client.pipeline(transaction=True) as pipe:
                pipe.json().get(
                    self._config.svc_name,
                    f"$.tags.{tag_id}"
                )

                res = await pipe.execute()
                tag_params = res[0][0]

                if not tag_params:
                    self._logger.warning(f"Тег {mes[tag_id]} не привязан к хранилищу.")
                    return

                async with tag_params["ds"].acquire() as conn:
                    await conn.execute(
                        f'drop table if exists "{tag_params["table"]}"'
                    )

                pipe.json().delete(
                    self._config.svc_name,
                    f"$.tags.{tag_id}"
                )
                await pipe.execute()

            await client.aclose()
        except Exception as ex:
            self._logger.error(f"Ошибка отвязки тега: {ex}")

        self._logger.info(f"Тег {tag_id} отвязан от хранилища.")

    async def _write_tag_data_to_db(
            self, tag_id: str) -> None :

        # метод, переопределяемый в классах-потомках
        # записывает данные одного тега в хранилище
        self._logger.debug(f"Запись данных тега '{tag_id}' из кэша в хранилища...")

        try:
            client = redis.Redis(connection_pool=self._cache_pool)
            # добавим ключ "svc_name:ds_id": {}
            async with client.pipeline() as pipe:
                pipe.json().get(f"{self._config.svc_name}:{tag_id}", "$")
                pipe.json().set(f"{self._config.svc_name}:{tag_id}", "$.data", [])
                tag_cache = await pipe.execute()

                if not tag_cache[0][0]["data"]:
                    self._logger.info(f"Кэш данных тега {tag_id} пустой.")
                    return

                for ds_id in tag_cache[0][0]["dss"].keys():
                    active = await pipe.json().get(
                        f"{self._config.svc_name}:{ds_id}", "prsActive"
                    ).execute()
                    if active[0] is None:
                        self._logger.error(
                            f"Несоответствие кэша тега {tag_id} c кэшем хранилища {ds_id}")
                        continue

                    # если хранилище неактивно, данные в него не записываем
                    if not active[0]:
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
            self._logger.error(f"Ошибка записи данных в базу {ds_id}: {ex}")

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
        Для PostgreSQL в словаре конфигурации только один ключ - dsn.

        Args:
            config (dict): _description_
        """

        return await apg.create_pool(dsn=config["dsn"])

    async def _read_data(self, tag_id: str, start: int, finish: int,
        order: int, count: int, one_before: bool, one_after: bool, value: Any = None):

        actual_ds = None
        client = redis.Redis(connection_pool=self._cache_pool)
        async with client.pipeline() as pipe:
            tag_data = await pipe.json().get(
                f"{self._config.svc_name}:{tag_id}",
                "prsActive", "dss"
            ).execute()

            if not tag_data[0]:
                self._logger.error(f"Тег {tag_id} отсутствует в кэше.")
                await client.aclose()

                return []
            if not tag_data[0]["prsActive"]:
                self._logger.error(f"Тег {tag_id} неактивен.")
                await client.aclose()

                return []

            # если тег привязан к нескольким хранилищам, пока непонятна логика
            # из какого хранилища брать данные.
            # пока будем брать из первого активного
            for ds_id in tag_data[0]["dss"].keys():
                ds_res = await pipe.json().get(
                    f"{self._config.svc_name}:{ds_id}",
                    "prsActive"
                ).execute()
                if ds_res[0] is None:
                    self._logger.error(
                        f"Хранилище {ds_id} отсутствует в кэше."
                    )
                if ds_res[0]:
                    actual_ds = ds_id
                    break
        await client.aclose()

        if not actual_ds:
            self._logger.error(
                f"Не найдено актуальное хранилище для тега {tag_id}"
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
