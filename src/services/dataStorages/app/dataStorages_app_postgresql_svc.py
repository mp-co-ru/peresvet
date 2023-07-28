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

from ldap.dn import str2dn, dn2str

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

    def _set_incoming_commands(self) -> dict:
        return {
            "tags.downloadData": self._tag_get,
            "tags.uploadData": self._tag_set,
            "dataStorages.linkTag": self._link_tag,
            "dataStorages.unlinkTag": self._unlink_tag
        }

    async def _reject_message(self, mes: dict) -> bool:
        return False

    async def _link_tag(self, mes: dict) -> dict:
        """Метод привязки тега к хранилищу.
        Атрибут ``prsStore`` должен быть вида
        ``{"tableName": "<some_table>"}`` либо отсутствовать

        Args:
            mes (dict): {
                "action": "datastorages.linktag",
                "data": {
                    "tagId": "tag_id",
                    "dataStorageId": "ds_id",
                    "attributes": {
                        "prsStore": {"tableName": "<some_table>"}
                    }
                }

        """

        async with self._connection_pools[mes["data"]["dataStorageId"]].acquire() as conn:

            mes["data"]["attributes"].setdefault(
                "prsStore",
                {"tableName": f't_{mes["data"]["tagId"]}'}
            )

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

    async def _tag_set(self, mes: dict) -> None:
        """

        Args:
            mes (dict): {
                "action": "tags.set_data",
                "data": {
                    "data": [
                        {
                            "tagId": "<some_id>",
                            "data": [(x, y, q)]
                        }
                    ]
                }
            }
        """
        async def set_tag_data(payload: dict) -> None:
            self._logger.info(f"Запись данных тега {payload['tagId']}")

            tag_params = self._tags.get(payload["tagId"])
            if not tag_params:
                self._logger.error(
                    f"Тег {payload['tagId']} не привязан к хранилищу."
                )
                return

            connection_pool = tag_params["ds"]
            tag_tbl = tag_params["table"]
            tag_value_type = tag_params["value_type"]
            update = tag_params["update"]
            data_items = payload["data"]

            if tag_value_type == 4:
                new_data_items = []
                for item in data_items:
                    new_data_items.append(
                        (item[0], json.dumps(item[1], ensure_ascii=False), item[2])
                    )
                data_items = new_data_items

            try:
                async with connection_pool.acquire() as conn:
                    async with conn.transaction(isolation='read_committed'):
                        if update:
                            xs = [str(x) for x, _, _ in data_items]
                            q = f'delete from "{tag_tbl}" where x in ({",".join(xs)}); '
                            await conn.execute(q)

                        await conn.copy_records_to_table(
                            tag_tbl,
                            records=data_items,
                            columns=('x', 'y', 'q'))

                '''
                await self._post_message(mes={
                        "action": "dataStorages.tagsArchived",
                        "data": payload
                    },
                    reply=False, routing_key=payload["tagId"]
                )
                '''

            except PostgresError as ex:
                self._logger.error(f"Ошибка при записи данных тега {payload['tagId']}: {ex}")

        for tag_data in mes["data"]["data"]:
            await set_tag_data(tag_data)

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
                    self._logger.info(f"Связь с базой данных {dsn} установлена.")
                    connected = True
                except Exception as ex:
                    self._logger.error(f"Ошибка связи с базой данных '{dsn}': {ex}")
                    await asyncio.sleep(5)

            search_tags = {
                "base": ds[0],
                "filter": {
                    "objectClass": ["prsDatastorageTagData"]
                },
                "attributes": ["prsStore", "cn"]
            }

            self._logger.info("Чтение тегов, привязанных к хранилищу...")

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
                self._tags[tag_id] = tag_cache

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
                '''
                if not alert[0]:
                    continue
                '''

                alert_id = alert[2]["cn"][0]

                get_alert_data = {
                    "id": [alert_id],
                    "attributes": ["prsActive"]
                }

                alert_data = await self._hierarchy.search(payload=get_alert_data)

                if not alert_data:
                    self._logger.info(f'Не найдена тревога {alert_id}')
                    continue

                self._alerts[alert_id] = {
                    "ds": self._connection_pools[ds[0]],
                    "table": json.loads(alert[0][2]["prsStore"][0])["table"],
                    "active": alert_data[0][2]["prsActive"][0] == "TRUE"
                }

                await self._amqp_consume["queue"].bind(
                    exchange=self._amqp_consume["alerts"]["exchange"],
                    routing_key=alert_id
                )

            self._logger.info(f"Хранилище {ds[0]}. Тревоги прочитаны.")

    async def on_startup(self) -> None:
        await super().on_startup()
        try:
            await self._connect_to_db()
        except Exception as ex:
            self._logger.error(f"Ошибка связи с базой данных: {ex}")


    """"
    class PrsReqGetData(BaseModel):
        tagId: str | List[str] = Field(None,
            title="Тег(-и)",
            description=(
                "Идентификатор тега или массив идентификаторов."
            )
        )
        start: int | str = Field(None, title="Начало периода",
            description=(
                "Может быть либо целым числом, в этом случае это микросекунды, "
                "либо строкой в формате ISO8601."
        )
        )

        finish: int | str = Field(None, title="Конец периода",
            description=(
                "Может быть либо целым числом, в этом случае это микросекунды, "
                "либо строкой в формате ISO8601."
        )
        )

        #finish: int | str = None
        maxCount: int = Field(None, title="Максимальное количество точек",
            description=(
                "Максимальное количество точек, возвращаемых для одного тега. "
                "Если в хранилище для запрашиваемого периода находится "
                "больше, чем maxCount точек, то в этом случае данные будут "
                "интерполированы и возвращено maxCount точек. "
                "Пример использования данной функциональности: "
                "тренд на экране отображает значения тега за определённый период."
                "Период пользователем может быть указан очень большим "
                "и в хранилище для этого периода может быть очень много точек. "
                "Но сам тренд на экране при этом имеет ширину, предположим, "
                "800 точек и, соответственно, больше 800 точек не может "
                "отобразить, поэтому и возвращать большее количество точек "
                "не имеет смысла. В таком случае в ответе на запрос будет "
                "выставлен флаг `excess` (для каждого тега в массиве `data`)."
            )
        )
        format: bool | str = Field(False, title="Форматирование меток времени",
            description=(
                "Если присутствует и равен `true`, то метки времени будут "
                "возвращены в виде строк в формате ISO8601 и с часовой зоной "
                "сервера."
            )
        )
        actual: bool = Field(False, title="Актуальные значение",
            description=(
                "Если присутствует и равен `true`, то будут возвращены только "
                "реально записанные в хранилище значения."
            )
        )

        value: Any = Field(None, title="Значение для поиска",
            description="Фильтр по значению")

        count: int = Field(None, title="Количество возвращаемых значений")

        timeStep: int = Field(None, title="Период между соседними возвращаемыми значениями")

        @validator('tagId', always=True)
        def tagId_must_exists(cls, v):
            if v is None:
                raise ValueError("Должен присутствовать ключ 'tagId'")
            if isinstance(v, str):
                return [v]
            return v

        # always=True, because if finish is None it is set to current time
        @validator('finish', always=True)
        def finish_set_to_int(cls, v):
            return t.ts(v)

        # if start is None, validator will not be called
        @validator('start')
        def convert_start(cls, v):
            return t.ts(v)

        @validator('maxCount')
        def maxCount_not_zero(cls, v):
            if v is None:
                return v

            if isinstance(v, int) and v > 0:
                return v

            raise ValueError("Параметр maxCount должен быть целым числом и больше нуля.")
    """


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

        self._logger.debug(f"Tasks done")

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
            self, tag_data: List[dict], value: List[Any], tag_type_code: int,
            tag_step: bool) -> List[dict]:
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
                    y = json.loads(item['y'])
                else:
                    y = item['y']
                if y in value:
                    res.append(item)
        else:
            for i in range(1, len(tag_data)):
                y1 = tag_data[i - 1]['y']
                y2 = tag_data[i]['y']
                x1 = tag_data[i - 1]['x']
                x2 = tag_data[i]['x']
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
                            res.append({"x": x, "y": val})
            if tag_data[-1]['y'] in value:
                res.append(tag_data[-1])
        return res

    async def _data_get_interpolated(self,
                                     tag_cache: dict,
                                     start: int,
                                     finish: int,
                                     count: int,
                                     time_step: int) -> List[dict]:
        """ Получение интерполированных значений с шагом time_step
        """
        tag_data = await self._data_get_many(tag_cache,
            start or (finish - time_step * (count - 1)),
            finish, None
        )
        # Создание ряда таймстэмпов с шагом `time_step`
        time_row = self._timestep_row(time_step, count, start, finish)

        if not tag_data:
            return [{'x': x, 'y': None, 'q': None} for x in time_row]

        return self._interpolate(tag_data, time_row)

    def _interpolate(self, raw_data: List[dict], time_row: List[int]) -> List[dict]:
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
        none_indexes = [idx for idx, val in enumerate(raw_data) if val['y'] is None]
        size = len(raw_data)
        try:
            splitted_by_none = [raw_data[i: j+1] for i, j in
                zip([0] + none_indexes, none_indexes +
                ([size] if none_indexes[-1] != size else []))]
        except IndexError:
            splitted_by_none = [raw_data]

        data = []  # Результирующий список
        for period in splitted_by_none:
            if len(period) == 1:
                continue

            key_x = lambda d: d['x']
            min_ts = min(period, key=key_x)['x']
            max_ts = max(period, key=key_x)['x']
            is_last_period = period == splitted_by_none[-1]

            # В каждый подсписок добавляются значения из ряда ``time_row``
            period = [{'x': ts, 'y': None,'q': None} \
                      for ts in time_row if min_ts <= ts < max_ts] + period
            period.sort(key=key_x)

            if not is_last_period:
                period.pop()

            # Расширенный подсписок заворачивается в DataFrame и индексируется по 'x'
            df = pd.DataFrame(
                period,
                index=[r['x'] for r in period]
            ).drop_duplicates(subset='x', keep='last')

            # линейная интерполяция значений 'y' в датафрейме для числовых тэгов
            # заполнение NaN полей ближайшими не-NaN для нечисловых тэгов
            df[['x', 'y']] = df[['x', 'y']].interpolate(
                method=('pad', 'index')[is_numeric_dtype(df['y'])]
            )

            # None-значения 'q' заполняются ближайшим не-None значением сверху
            df['q'].fillna(method='ffill', inplace=True)

            # Удаление из датафрейма всех элементов, чьи 'x' не принадлежат ``time_row``
            df = df.loc[df['x'].isin(time_row)]
            df[['y', 'q']] = df[['y', 'q']].replace({np.nan: None})

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

    def _last_point(self, x: int, data: List[dict]) -> Tuple[int, Any]:
        return (x, list(filter(lambda rec: rec['x'] == x, data))[-1]['y'])

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
                return [{
                    'x': finish,
                    'y': None,
                    'q': None,
                }]

        x0 = tag_data[0]['x']
        y0 = tag_data[0]['y']
        try:
            x1, y1 = self._last_point(tag_data[1]['x'], tag_data)
            if not tag_cache["table"]:
                tag_data[0]['y'] = linear_interpolated(
                    (x0, y0), (x1, y1), finish
                )

            tag_data.pop()
        except IndexError:
            # Если в выборке только одна запись и `to` меньше, чем `x` этой записи...
            if x0 > finish:
                tag_data[0]['y'] = None
                tag_data[0]['q'] = None
        finally:
            tag_data[0]['x'] = finish

        return tag_data

    async def _data_get_many(self,
                             tag_cache: dict,
                             start: int,
                             finish: int,
                             count: int = None) -> List[dict]:
        """ Получение значения на текущую метку времени
        """
        tag_data = await self._read_data(
            tag_cache["table"], start, finish,
            (Order.CN_DESC if count is not None and start is None else Order.CN_ASC),
            count, True, True, None
        )
        if not tag_data:
            return []

        now_ms = t.ts()
        x0 = tag_data[0]['x']
        y0 = tag_data[0]['y']

        if start is not None:
            if x0 > start:
                # Если `from_` раньше времени первой записи в выборке
                tag_data.insert(0, {
                    'x': start,
                    'y': None,
                    'q': None,
                })

            if len(tag_data) == 1:
                if x0 < start:
                    tag_data[0]['x'] = start
                    tag_data.append({
                        'x': now_ms,
                        'y': y0,
                        'q': tag_data[0]['q'],
                    })
                return tag_data

            x1, y1 = self._last_point(tag_data[1]['x'], tag_data)
            if x1 == start:
                # Если время второй записи равно `from`,
                # то запись "перед from" не нужна
                tag_data.pop(0)

            if x0 < start < x1:
                tag_data[0]['x'] = start
                if tag_cache["step"]:
                    tag_data[0]['y'] = y0
                else:
                    tag_data[0]['y'] = linear_interpolated(
                        (x0, y0), (x1, y1), start
                    )

        if finish is not None:
            # (xn; yn) - запись "после to"
            xn = tag_data[-1]['x']
            yn = tag_data[-1]['y']

            # (xn_1; yn_1) - запись перед значением `to`
            try:
                xn_1, yn_1 = self._last_point(tag_data[-2]['x'], tag_data)
            except IndexError:
                xn_1 = -1
                yn_1 = None

            if xn_1 == finish:
                # Если время предпоследней записи равно `to`,
                # то запись "после to" не нужна
                tag_data.pop()

            if xn_1 < finish < xn:
                tag_data[-1]['x'] = finish
                tag_data[-1]['q'] = tag_data[-2]['q']
                if tag_cache["step"]:
                    tag_data[-1]['y'] = yn_1
                else:
                    tag_data[-1]['y'] = linear_interpolated(
                        (xn_1, yn_1), (xn, yn), finish
                    )

            if finish > xn:
                tag_data.append({
                    'x': finish,
                    'y': yn,
                    'q': tag_data[-1]['q'],
                })

        if all((finish is None, now_ms > tag_data[-1]['x'])):
            tag_data.append({
                'x': now_ms,
                'y': tag_data[-1]['y'],
                'q': tag_data[-1]['q'],
            })

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
                    records.append(dict(r))
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
