import sys
import copy
import json
import asyncio
from ldap.dn import str2dn, dn2str

sys.path.append(".")

from dataStorages_app_postgresql_settings import DataStoragesAppPostgreSQLSettings
from src.common import svc
from src.common import hierarchy

import asyncpg as apg
from asyncpg.exceptions import PostgresError

class DataStoragesAppPostgreSQL(svc.Svc):

    def __init__(
            self, settings: DataStoragesAppPostgreSQLSettings, *args, **kwargs
        ):
        super().__init__(settings, *args, **kwargs)

        self._commands = {
            "tags.set": self._tag_set,
            "tags.get": self._tag_get
        }

        self._connection_pools = {}
        self._tags = {}
        self._alerts = {}

    async def _tag_set(self, mes: dict) -> None:
        """

        Args:
            mes (dict): {
                "action": "tagSet",
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
                async with self.conn_pool.acquire() as conn:
                    async with conn.transaction(isolation='read_committed'):
                        if update:
                            xs = [str(x) for x, _, _ in data_items]
                            q = f'delete from "{tag_tbl}" where x in ({",".join(xs)}); '
                            await conn.execute (q)

                        await conn.copy_records_to_table(
                            tag_tbl,
                            records=data_items,
                            columns=('x', 'y', 'q'))

                self._post_message(mes={
                        "action": "tagArchived",
                        "data": payload
                    },
                    reply=False, routing_key=payload["tagId"]
                )

            except PostgresError as ex:
                svc.logger.error(f"Ошибка при записи данных тега {payload['tagId']}: {ex}")

        tasks = []
        for tag_data in mes["data"]["data"]:
            future = asyncio.create_task(set_tag_data(tag_data))
            tasks.append(future)

        await asyncio.wait(
            tasks, return_when=asyncio.ALL_COMPLETED
        )

    async def on_startup(self) -> None:
        await super().on_startup()

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

        payload["attributes"] = ["prsJsonConfigString"]

        async for ds in self._hierarchy.search(payload=payload):
            if not ds[0]:
                continue

            self._logger.info(f"Чтение данных о хранилище {ds[0]}...")

            dsn = json.loads(ds[2]["prsJsonConfigString"][0])["dsn"]

            self._connection_pools[ds[0]] = await apg.create_pool(dsn=dsn)

            search_tags = {
                "base": ds[0],
                "filter": {
                    "objectClass": ["prsDatastorageTagData"]
                },
                "attributes": ["prsStore"]
            }
            async for tag in self._hierarchy.search(payload=search_tags):
                if not tag[0]:
                    continue

                get_tag_data = {
                    "id": [tag[0]],
                    "attributes": [
                        "prsUpdate", "prsValueTypeCode", "prsActive", "prsStep"
                    ]
                }

                tag_data = await anext(
                    self._hierarchy.search(payload=get_tag_data)
                )
                if not tag_data[0]:
                    self._logger.info(f"Не найден тег {tag[0]}")
                    continue

                self._tags[tag[0]] = {
                    "ds": self._connection_pools[ds[0]],
                    "table": json.loads(tag[2]["prsStore"][0])["table"],
                    "active": tag_data[2]["prsActive"][0] == "TRUE",
                    "update": tag_data[2]["prsUpdate"][0] == "TRUE",
                    "value_type": int(tag_data[2]["prsValueTypeCode"][0]),
                    "step": tag_data[2]["prsStep"][0] == "TRUE"
                }

                await self._amqp_consume["queue"].bind(
                    exchange=self._amqp_consume["tags"]["exchange"],
                    routing_key=tag[0]
                )

            self._logger.info(f"Хранилище {ds[0]}. Теги прочитаны.")

            search_alerts = {
                "base": ds[0],
                "filter": {
                    "objectClass": ["prsDatastorageAlertData"]
                },
                "attributes": ["prsStore"]
            }
            async for alert in self._hierarchy.search(payload=search_alerts):
                if not alert[0]:
                    continue

                get_alert_data = {
                    "id": [alert[0]],
                    "attributes": ["prsActive"]
                }

                alert_data = await anext(
                    self._hierarchy.search(payload=get_alert_data)
                )
                if not alert_data[0]:
                    self._logger.info(f"Не найдена тревога {alert[0]}")
                    continue

                self._alerts[alert[0]] = {
                    "ds": self._connection_pools[ds[0]],
                    "table": json.loads(alert[2]["prsStore"][0])["table"],
                    "active": alert_data[2]["prsActive"][0] == "TRUE"
                }

                await self._amqp_consume["queue"].bind(
                    exchange=self._amqp_consume["alerts"]["exchange"],
                    routing_key=alert[0]
                )

            self._logger.info(f"Хранилище {ds[0]}. Тревоги прочитаны.")


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
                "action": "tag.get",
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

        tasks = {}
        tag_types = {}
        for tag_id in mes["tagId"]:
            tag_params = self._tags.get(tag_id)
            if not tag_params:
                self._logger.error(
                    f"Тег {tag_id} не привязан к хранилищу."
                )
                return {}

            tag_types[tag_id] = {
                "type": tag_params["value_type"],
                "step": tag_params["step"],
                "table": tag_params["table"]
            }

            # Если ключ actual установлен в true, ключ timeStep не учитывается
            if mes["data"]["actual"] or (mes["data"]["value"] is not None \
               and len(mes["data"]["value"]) > 0):
                mes["data"]["timeStep"] = None

            if mes["data"]["actual"]:
                tasks[tag_id]= asyncio.create_task(
                        self._data_get_actual(
                            tag_types[tag_id]["table"],
                            mes["data"]["start"],
                            mes["data"]["finish"],
                            mes["data"]["count"],
                            mes["data"]["value"]
                        )
                    )

            elif mes["data"]["timeStep"] is not None:
                tasks[tag_id]= asyncio.create_task(
                        self._data_get_interpolated(
                            tag_types[tag_id]["table"],
                            mes["data"]["start"], mes["data"]["finish"],
                            mes["data"]["count"], mes["data"]["timeStep"],
                            tag_types[tag_id]["step"]
                        )
                    )

            elif mes["data"]["start"] is None and \
                mes["data"]["count"] is None and \
                (mes["data"]["value"] is None or len(mes["data"]["value"]) == 0):
                tasks[tag_id] = asyncio.create_task(
                        self._data_get_one(
                            tag_types[tag_id]["table"],
                            mes["data"]["finish"],
                            mes["data"]["step"]
                        )
                    )

            else:
                # Множество значений
                tasks[tag_id]= asyncio.create_task(
                        self._data_get_many(
                            tag_types[tag_id]["table"],
                            mes["data"]["start"],
                            mes["data"]["finish"],
                            mes["data"]["count"],
                            tag_types[tag_id]["step"]
                        )
                    )

        await asyncio.wait(list(tasks.values()))

        result = {"data": []}
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
                    tag_types[tag_id]['type'],
                    tag_types[tag_id]['step']
                )
                if mes["data"]["from_"] is None:
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
