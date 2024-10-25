import sys
import json
import aiohttp
import numbers
import copy
from typing import Any, List, Tuple
import pandas as pd
from pandas.api.types import is_numeric_dtype
import numpy as np
import time

sys.path.append(".")

from src.common import svc
import src.common.times as t
from src.common.consts import (
    CNTagValueTypes as TVT,
    Order
)
from src.services.dataStorages.app.victoriametrics.dataStorages_app_victoriametrics_settings import DataStoragesAppVictoriametricsSettings

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

class DataStoragesAppVictoriametrics(svc.Svc):

    def __init__(
            self, settings: DataStoragesAppVictoriametricsSettings, *args, **kwargs
        ):
        super().__init__(settings, *args, **kwargs)

        # "putUrl": "http://ws_vm:4242/api/put",
        # "getUrl": "http://localhost:8428/api/v1/query_range?query=tag1&start=1691131350000"

        self._connection_pools = {}
        self._tags = {}
        self._alerts = {}

    def _set_handlers(self) -> dict:
        return {
            "tags.downloadData": self._tag_get,
            "tags.uploadData": self._tag_set,
            "dataStorages.linkTag": self._link_tag,
            "dataStorages.unlinkTag": self._unlink_tag,
            "dataStorages.updated": self._updated
        }

    async def _updated (self, mes: dict) -> None:
        pass

    async def _reject_message(self, mes: dict) -> bool:
        return False

    # fixed
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

        # имя метрики не может начинаться с цифр и не может содержать дефисов
        mes["data"]["attributes"].setdefault(
            "prsStore",
            {"metric": f'{mes["data"]["tagId"].replace("-", "_")}'}
        )

        tag_params = self._tags.get(mes["data"]["tagId"])
        if tag_params:
            metric = tag_params['metric']
            if mes["data"]["attributes"]["prsStore"]["metric"] == metric:
                self._logger.warning(f"Тег {mes['data']['tagId']} уже привязан")
                return

        metric = mes["data"]["attributes"]["prsStore"]["metric"]

        tag_cache = await self._prepare_tag_data(
            mes["data"]["tagId"],
            mes["data"]["dataStorageId"]
        )
        tag_cache["metric"] = metric
        cache_for_store = copy.deepcopy(tag_cache)

        tag_cache["ds"] = self._connection_pools[mes["data"]["dataStorageId"]]
        self._tags[mes["data"]["tagId"]] = tag_cache

        return {
            "prsStore": json.dumps(cache_for_store)
        }

    # fixed
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

        self._tags.pop(mes["data"]["tagId"])

        self._logger.info(f"{self._config.svc_name} :: Тег {mes['data']['tagId']} отвязан от хранилища.")

    # fixed
    async def _tag_set(self, mes: dict) -> None:
        """

        Args:
            mes (dict): {
                "action": "tags.set_data",
                "data": {
                    "data": [
                        {
                            "tagId": "<some_id>",
                            "data": [(y, x, q)]
                        }
                    ]
                }
            }
        """
        async def set_tag_data(payload: dict) -> None:
            self._logger.info(f"{self._config.svc_name} :: Запись данных тега {payload['tagId']}")

            tag_params = self._tags.get(payload["tagId"])
            if not tag_params:
                self._logger.error(
                    f"{self._config.svc_name} :: Тег {payload['tagId']} не привязан к хранилищу."
                )
                return

            connection = tag_params["ds"]
            metric = tag_params["metric"]
            tag_value_type = tag_params["value_type"]
            update = tag_params["update"]
            data_items = payload["data"]

            formatted_data = []
            for item in data_items:
                y, x, _ = item
                vm_data_item = {
                    'metric': metric,
                    'value': (y, json.dumps(y, ensure_ascii=False))[tag_value_type == 4],
                    'timestamp': round(x / 1000)
                }
                formatted_data.append(vm_data_item)

            resp = await connection["conn"].post(connection["putUrl"], json=formatted_data)

            self._logger.debug(f"Set data status: {resp.status}")

        for tag_data in mes["data"]["data"]:
            await set_tag_data(tag_data)

    # fixed
    async def _prepare_tag_data(self, tag_id: str, ds_id: str) -> dict | None:
        get_tag_data = {
            "id": [tag_id],
            "attributes": [
                "prsUpdate", "prsValueTypeCode", "prsActive", "prsStep"
            ]
        }

        tag_data = await self._hierarchy.search(payload=get_tag_data)

        if not tag_data:
            self._logger.info(f"{self._config.svc_name} :: Не найден тег {tag_id}")
            return None

        to_return = {
            "metric": None,
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

        to_return["metric"] = json.loads(link_data[0][2]["prsStore"][0])["metric"]

        return to_return

    # fixed
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
            await self._amqp_consume_queue["queue"].unbind(
                    exchange=self._amqp_consume_queue["exchanges"]["main"]["exchange"],
                    routing_key=self._config.consume["exchanges"]["main"]["routing_key"][0]
                )

        payload["attributes"] = ["prsJsonConfigString"]

        dss = await self._hierarchy.search(payload=payload)
        for ds in dss:
            await self._amqp_consume_queue["queue"].bind(
                exchange=self._amqp_consume_queue["exchanges"]["main"]["exchange"],
                routing_key=ds[0]
            )

            self._logger.info(f"{self._config.svc_name} :: Чтение данных о хранилище {ds[0]}...")

            urls = json.loads(ds[2]["prsJsonConfigString"][0])

            conn = aiohttp.TCPConnector()
            self._connection_pools[ds[0]] = {
                "conn": aiohttp.ClientSession(connector=conn),
                "putUrl": urls["putUrl"],
                "getUrl": urls["getUrl"]
            }
            self._logger.info(f"{self._config.svc_name} :: Связь с базой данных {ds[0]} установлена.")

            search_tags = {
                "base": ds[0],
                "filter": {
                    "objectClass": ["prsDatastorageTagData"]
                },
                "attributes": ["prsStore", "cn"]
            }

            self._logger.info(f"{self._config.svc_name} :: Чтение тегов, привязанных к хранилищу...")

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
                await self._amqp_consume_queue["queue"].bind(
                    exchange=self._amqp_consume_queue["exchanges"]["tags"]["exchange"],
                    routing_key=tag_id
                )

                self._logger.debug(f"Тег {tag_id} привязан ({i}). Время: {time.time() - t1}")
                i += 1

            self._logger.info(f"{self._config.svc_name} :: Хранилище {ds[0]}. Теги прочитаны.")

            """
            search_alerts = {
                "base": ds[0],
                "filter": {
                    "objectClass": ["prsDatastorageAlertData"]
                },
                "attributes": ["prsStore", "cn"]
            }

            self._logger.info(f"{self._config.svc_name} :: Чтение тревог, привязанных к хранилищу...")

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
                    self._logger.info(f"{self._config.svc_name} :: Не найдена тревога {alert_id}')
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

            self._logger.info(f"{self._config.svc_name} :: Хранилище {ds[0]}. Тревоги прочитаны.")
            """

    # fixed
    async def on_startup(self) -> None:
        await super().on_startup()
        try:
            await self._connect_to_db()
        except Exception as ex:
            self._logger.error(f"{self._config.svc_name} :: Ошибка связи с базой данных: {ex}")

    # fixed
    async def _tag_get(self, mes: dict) -> dict:
        """_summary_

        Args:
            mes (dict): {`
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

        ds_with_tags = {}
        for tag_id in mes["data"]["tagId"]:
            tag_params = self._tags.get(tag_id)
            if not tag_params:
                self._logger.error(
                    f"{self._config.svc_name} :: Тег {tag_id} не привязан к хранилищу."
                )
                continue

            ds_with_tags.setdefault(
                tag_params["ds"]["getUrl"],
                {
                    "conn": tag_params["ds"]["conn"],
                    "tags": []
                }
            )
            ds_with_tags[tag_params["ds"]["getUrl"]]["tags"].append(tag_params["metric"])

        query_part = ""
        if mes["data"]["start"]:
            query_part = f"&start={mes['data']['start']/1000000}"
        if mes["data"]["finish"]:
            query_part = f"&{query_part}end={mes['data']['finish']/1000000}"
        if mes["data"]["timeStep"]:
            query_part = f"&{query_part}step={mes['data']['timeStep']/1000000}"

        # допущение: метрика тега - id тега.
        res_data = {"data": []}
        for key, value in ds_with_tags.items():
            metrics = f'({",".join(value["tags"])})'
            full_url = f"{key}?query={metrics}{query_part}"

            async with value["conn"].get(full_url) as response:
                res_json = await response.json()

                if res_json["status"] == "success":

                    for item in res_json["data"]["result"]:
                        tag_item = {
                            "tagId": item["metric"]["__name__"].replace("_", "-"),
                            "data": []
                        }
                        for val in item["values"]:
                            match self._tags.get(tag_item["tagId"])["value_type"]:
                                case 0:
                                    value = int(val[1])
                                case 1:
                                    value = float(val[1])
                                case 2:
                                    value = val[1]
                                case 4:
                                    value = json.loads(val[1])

                            data_item = [
                                value,
                                val[0] * 1000000,
                                None
                            ]
                            tag_item["data"].append(data_item)

                        res_data["data"].append(tag_item)
                else:
                    self._logger.error(f"{self._config.svc_name} :: Ошибка получения данных: {res_json}")

        self._logger.debug(f"Data get result: {res_data}")

        return res_data

    # fixed
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

    # fixed
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

    # fixed
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

    # fixed
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

    # fixed
    def _last_point(self, x: int, data: List[tuple]) -> Tuple[int, Any]:
        return (x, list(filter(lambda rec: rec[1] == x, data))[-1][0])

    # fixed
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

    # fixed
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

    # fixed
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

        #prsJsonConfigString	{"putUrl": "http://ws_vm:4242/api/put", "getUrl": "http://ws_vm:8428/api/v1/export"}

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

settings = DataStoragesAppVictoriametricsSettings()

app = DataStoragesAppVictoriametrics(settings=settings, title="DataStoragesAppPostgreSQL")
