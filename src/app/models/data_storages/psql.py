import json
import copy
from typing import Dict, Any, List, Tuple
import asyncio

from urllib.parse import urlparse
from fastapi import HTTPException, Response

import pandas as pd
from pandas.api.types import is_numeric_dtype
import numpy as np
import numbers

import asyncpg as apg
from asyncpg.exceptions import PostgresError

from pydantic import validator, root_validator

from app.models.DataStorage import PrsDataStorageEntry, PrsDataStorageCreate
from app.models.Data import PrsReqGetData
from app.models.Tag import PrsTagEntry
from app.svc.Services import Services as svc
from app.const import CNHTTPExceptionCodes as HEC, CNTagValueTypes as TVT, Order
import app.times as t


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

'''
class PrsPostgreSQLCreate(PrsDataStorageCreate):

    @root_validator
    # этот валидатор должен быть в классах конкретных хранилищ
    @classmethod
    def check_config(cls, values):

        def uri_validator(x):
            result = urlparse(x)
            return all([result.scheme, result.netloc])

        attrs = values.get('attributes')
        if not attrs:
            raise ValueError((
                "При создании хранилища необходимо задать атрибуты."
            ))

        config = attrs.get('prsJsonConfigString')

        if not config:
            raise ValueError((
                "Должна присутствовать конфигурация (атрибут prsJsonConfigString)."
            ))
            #TODO: методы класса создаются при импорте, поэтому jsonConfigString = None
            # и возникает ошибка

        try:
            if isinstance(config, str):
                config = json.loads(config)

            dsn = config["dsn"]
            if uri_validator(dsn):
                return values
        except Exception as ex:
            raise ValueError((
                "Конфигурация (атрибут prsJsonConfigString) для PostgreSQL должна быть вида:\n"
                "{'dsn': 'postgres://<user>:<password>@<host>:<port>/<database>?<option>=<value>'"
            )) from ex
'''

class PrsPostgreSQLEntry(PrsDataStorageEntry):

    def __init__(self, **kwargs):
        super(PrsPostgreSQLEntry, self).__init__(**kwargs)

        self.tag_cache = {}
        if isinstance(self.data.attributes.prsJsonConfigString, dict):
            js_config = self.data.attributes.prsJsonConfigString
        else:
            js_config = json.loads(self.data.attributes.prsJsonConfigString)

        self.dsn = js_config["dsn"]
        self.conn_pool = None

    async def _post_init(self):
        try:
            self.conn_pool = await apg.create_pool(dsn=self.dsn, min_size=20, max_size=200)
        except OSError as ex:
            er_str = f"Ошибка связи с базой данных '{self.dsn}': {ex}"
            svc.logger.error(er_str)
            raise HTTPException(HEC.CN_503, er_str) from ex

        await super(PrsPostgreSQLEntry, self)._post_init()

    def _format_tag_cache(self, tag: PrsTagEntry) -> None | str | Dict:
        # метод возращает данные, которые будут использоваться в качестве
        # кэша для тэга
        #res = json.loads(tag.data.attributes.prsStore)
        #res["u"] = tag.data.attributes.prsUpdate
        return {
            "attrs": tag.data.attributes.copy(deep=True)
        }

    def _format_tag_data_store(self, tag: PrsTagEntry) -> None | Dict:

        if not tag.data.attributes.prsStore:
            return {
                'table': f"t_{tag.id}"
            }

        try:
            _ = json.loads(tag.data.attributes.prsStore)["table"]
        except json.JSONDecodeError as _:
            svc.logger.error((
                f"Для тега id:{tag.id}, dn={tag.dn} неверный формат атрибута `smtStore`. "
                "Формат атрибута: {'table': '<table_name>'}"
            ))
            return

        return json.loads(tag.data.attributes.prsStore)

    async def connect(self) -> int:
        return 0

    async def create_tag_store(self, tag: PrsTagEntry):

        async with self.conn_pool.acquire() as conn:
            tbl_name = tag.data.attributes.prsStore['table']

            q = (
                    f"SELECT EXISTS ("
                    f"SELECT FROM information_schema.tables "
                    f"WHERE  table_name = '{tbl_name}')"
                )
            res = await conn.fetchval(q)
            if not res:

                if tag.data.attributes.prsValueTypeCode == TVT.CN_INT:
                    s_type = "bigint"
                elif tag.data.attributes.prsValueTypeCode == TVT.CN_DOUBLE:
                    s_type = "double precision"
                elif tag.data.attributes.prsValueTypeCode == TVT.CN_STR:
                    s_type = "text"
                elif tag.data.attributes.prsValueTypeCode == TVT.CN_JSON:
                    s_type = "jsonb"
                else:
                    er_str = f"Тег: {tag.id}; неизвестный тип данных: {tag.data.attributes.prsValueTypeCode}"
                    svc.logger.error(er_str)
                    raise HTTPException(HEC.CN_422, er_str)
            # -------------------------------------------------------------------------

                # Запрос на создание таблицы в РСУБД
                query = (f'CREATE TABLE public."{tbl_name}" ('
                    f'"id" serial primary key,'
                    f'"x" bigint NOT NULL,'
                    f'"y" {s_type},'
                    f'"q" int);'
                    # Создание индекса на поле "метка времени" ("ts")
                    f'CREATE INDEX "{tbl_name}_idx" ON public."{tbl_name}" '
                    f'USING btree ("x");')

                if tag.data.attributes.prsValueTypeCode == 4:
                    query += (f'CREATE INDEX "{tbl_name}_json__idx" ON public."{tbl_name}" '
                                'USING gin ("y" jsonb_path_ops);')


                await conn.execute(query)

    async def data_get(self, data: PrsReqGetData) -> Response:

        tasks = {}
        tag_types = {}
        for tag_id in data.tagId:
            tag_cache = svc.get_tag_cache(tag_id, "data_storage")
            if not tag_cache:
                svc.logger.error(f'Тег {tag_id} отсутствует.')
                continue

            tag_attrs = tag_cache['attrs']
            tag_table = tag_attrs.prsStore['table']
            tag_step = tag_attrs.prsStep
            tag_types[tag_id] = {
                "type": tag_attrs.prsValueTypeCode,
                "step": tag_step,
                "table": tag_table
            }

            # Если ключ actual установлен в true, ключ timeStep не учитывается
            if data.actual or (data.value is not None and len(data.value) > 0):
                data.timeStep = None

            if data.actual:
                tasks[tag_id]= asyncio.create_task(
                        self._data_get_actual(
                            tag_table, data.start, data.finish,
                            data.count, data.value
                        )
                    )

            elif data.timeStep is not None:
                tasks[tag_id]= asyncio.create_task(
                        self._data_get_interpolated(
                            tag_table, data.start, data.finish,
                            data.count, data.timeStep, tag_step
                        )
                    )

            elif data.start is None and data.count is None and (data.value is None or len(data.value) == 0):
                tasks[tag_id] = asyncio.create_task(
                        self._data_get_one(
                            tag_table, data.finish, tag_step
                        )
                    )

            else:
                # Множество значений
                tasks[tag_id]= asyncio.create_task(
                        self._data_get_many(
                            tag_table, data.start, data.finish,
                            data.count, tag_step
                        )
                    )

        await asyncio.wait(list(tasks.values()))

        result = {"data": []}
        for tag_id, task in tasks.items():
            tag_data = task.result()

            if not data.actual and (data.value is not None and len(data.value) > 0):
                tag_data = self._filter_data(tag_data, data.value, tag_types[tag_id]['type'], tag_types[tag_id]['step'])
                if data.from_ is None:
                    tag_data = [tag_data[-1]]

            excess = False
            if data.maxCount is not None:
                excess = len(tag_data) > data.max_count

                if excess:
                    if data.maxCount == 0:
                        tag_data = []
                    elif data.maxCount == 1:
                        tag_data = tag_data[:1]
                    elif data.maxCount == 2:
                        tag_data = [tag_data[0], tag_data[-1]]
                    else:
                        new_tag_data = tag_data[:data.maxCount - 1]
                        new_tag_data.append(tag_data[-1])
                        tag_data = new_tag_data

            if data.format:
                svc.format_data(tag_data, data.format)

            new_item = {
                "tagId": tag_id,
                "data": tag_data
            }
            if data.maxCount:
                new_item["excess"] = excess
            result["data"].append(new_item)

        return result

    def _filter_data(self, tag_data: List[dict], value: List[Any], tag_value_code: int, tag_step: bool) -> List[dict]:
        def estimate(x1: int, y1: int | float, x2: int, y2: int | float, y: int | float) -> int:
            '''
            Функция принимает на вход две точки прямой и значение, координату X которого возвращает.
            '''
            k = (y2 - y1)/(x2 - x1)
            b = y2 - k * x2

            x = round((y - b) / k)

            return x


        res = []
        if tag_step or tag_value_code not in [0, 1]:
            for item in tag_data:
                if tag_value_code == 4:
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
                        if tag_value_code == 0 and isinstance(val, float):
                            continue
                        if ((y1 > val and y2 < val) or (y1 < val and y2 > val)):
                            x = estimate(x1, y1, x2, y2, val)
                            res.append({"x": x, "y": val})
            if tag_data[-1]['y'] in value:
                res.append(tag_data[-1])
        return res

    async def _data_get_actual(self, table: str, start: int, finish: int,
            count: int, value: Any = None):

        order = Order.CN_ASC
        if start is None:
            order = Order.CN_DESC
            count = (1, count)[bool(count)]

        raw_data = await self._read_data(
            table, start, finish, order, count, False, False, value
        )

        return raw_data

    async def _data_get_interpolated(self,
                                     table: str,
                                     start: int,
                                     finish: int,
                                     count: int,
                                     time_step: int,
                                     tag_step: bool = True) -> List[Dict]:
        """ Получение интерполированных значений с шагом time_step
        """
        tag_data = await self._data_get_many(table,
            start or (finish - time_step * (count - 1)),
            finish, None, tag_step=tag_step
        )
        # Создание ряда таймстэмпов с шагом `time_step`
        time_row = self._timestep_row(time_step, count, start, finish)

        if not tag_data:
            return [{'x': x, 'y': None, 'q': None} for x in time_row]

        return self._interpolate(tag_data, time_row)

    def _interpolate(self, raw_data: List[Dict], time_row: List[int]) -> List[Dict]:
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

    def _last_point(self, x: int, data: List[Dict]) -> Tuple[int, Any]:
        return (x, list(filter(lambda rec: rec['x'] == x, data))[-1]['y'])

    async def _data_get_one(self,
                            table: str,
                            finish: int,
                            tag_step: bool = True) -> List[Dict]:
        """ Получение значения на текущую метку времени
        """
        tag_data = await self._read_data(
            table=table, start=None, finish=finish, count=1,
            one_before=False, one_after=not tag_step, order=Order.CN_DESC
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
            if not tag_step:
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
                             table: str,
                             start: int,
                             finish: int,
                             count: int = None,
                             tag_step: bool = True) -> List[Dict]:
        """ Получение значения на текущую метку времени
        """
        tag_data = await self._read_data(
            table, start, finish, (Order.CN_DESC if count is not None and start is None else Order.CN_ASC),
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
                if tag_step:
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
                if tag_step:
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

    async def _read_data(self, table: str, start: int, finish: int,
        order: int, count: int, one_before: bool, one_after: bool, value: Any = None):

        #table = self._validate_container(table)
        conditions = ['TRUE']
        sql_select = f'SELECT id, x, y, q FROM "{table}"'

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
        async with self.conn_pool.acquire() as conn:
            async with conn.transaction():
                async for r in conn.cursor(*query_args):
                    records.append(dict(r))
        return records

    async def data_set(self, data: Dict):
        # data:
        # {
        #        "<tag_id>": [(x, y, q)]
        # }
        #

        null = "NULL"

        q = ""
        for tag_id in data.keys():
            tag_cache = svc.get_tag_cache(tag_id, "data_storage")
            tag_tbl = tag_cache["attrs"].prsStore["table"]
            tag_value_type = tag_cache["attrs"].prsValueTypeCode
            update = tag_cache["attrs"].prsUpdate
            data_items = data[tag_id]

            if update:
                xs = [str(x) for x, _, _ in data_items]
                q += f'delete from "{tag_tbl}" where x in ({",".join(xs)}); '

            for item in data_items:
                if tag_value_type in [1, 2]:
                    y = (null, item[1])[bool(item[1])]
                elif tag_value_type == 3:
                    y = (null, f"'{item[1]}'")[bool(item[1])]
                elif tag_value_type == 4:
                    y = (null, f"'{json.dumps(item[1])}'")[bool(item[1])]
                q += f'insert into "{tag_tbl}" (x, y, q) values ({item[0]}, {y}, {(null, item[2])[bool(item[2])]});'

        try:
            async with self.conn_pool.acquire() as conn:
                async with conn.transaction(isolation='read_committed'):
                    res = await conn.execute (q)
        except PostgresError as ex:
            svc.logger.debug(ex)
            raise HTTPException (HEC.CN_500, detail=str(ex)) from ex

        svc.logger.debug(res)

        return Response(status_code=204)

    def _limit_data(self,
                    tag_data: List[Dict],
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
