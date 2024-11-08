"""
Модуль содержит классы, описывающие входные данные для команд CRUD для тегов
и класс сервиса ``tags_api_crud_svc``\.
"""
import sys
import math

import pandas as pd

from fastapi import APIRouter

sys.path.append(".")

from src.common import svc
from src.common.api_crud_svc import valid_uuid
from src.services.tags.datafunc_app_api.datafunc_app_api_settings import DatafuncAppAPISettings
import src.common.times as t
from src.services.tags.app_api.tags_app_api_svc import TagsAppAPI, DataGet

class TagsAppAPIDatafunc(TagsAppAPI):

    async def data_get(self, payload: DataGet) -> dict:
        """Метод применяет к обычному результату data/get обработку pandas
        с целью высчитать накопительное значение времени по кодам.
        Возвращаемые родительским data/get'ом данные по одному тегу должны быть
        вида:
        [
            [<code>, <ts>]
            [<code>, <ts>]...
        ]

        Args:
            payload (DataGet): обычный вход для data/get

        Returns:
            dict: {
                "data": [
                    {
                        "tagId": "...",
                        "data": [
                            [{"<code>": <накопительное значение микросекунд>}, x]
                        ]
                    }

                ]
            }
        """
        final_ts = payload.finish
        format_ts = payload.format
        current_ts = t.int_to_local_timestamp(t.now_int())
        if format_ts:
            # если изначальный запрос с флагом format = true,
            # то удалим его и отформатируем время уже в конце
            final_ts = t.int_to_local_timestamp(final_ts)
            payload.format = False

        timeStep = payload.timeStep
        if timeStep:
            payload.timeStep = None

        res = await super().data_get(mes=payload)

        final_res = {
            "data": []
        }

        # для скорости не оптимизируем код, просто добавляем случай, когда
        # есть timeStep
        #TODO: оптимизировать код
        if not timeStep:
            for tag in res["data"]:
                df = pd.DataFrame(tag["data"], columns=['code', 'ts', 'q'])
                df = df.drop('q', axis=1).dropna().astype(int)
                df['ts'] = df['ts'].astype(int)

                df['duration'] = df['ts'].diff(periods=-1).fillna(0)
                df['duration'] = df['duration'] * (-1)
                df = df.groupby('code')['duration'].sum()

                df = df.astype(int)

                final_value = df.to_dict()

                final_res['data'].append({
                    "tagId": tag["tagId"],
                    "data": [
                        (final_value, final_ts, None)
                    ]
                })

        else:

            for tag in res["data"]:
                data = tag["data"]
                final_data = []
                if data:
                    df = pd.DataFrame(data=data,columns=["code", "ts", "q"])
                    df = df.drop('q', axis=1)
                    #df['ts'] = df['ts'].astype(int)
                    df['date'] = df['ts'].apply(t.int_to_local_timestamp)

                    codes = df["code"].unique()
                    # TODO: получается, поддерживаем в этом методе только
                    # целочисленные теги, исправить
                    codes = [int(i) for i in codes if not math.isnan(i)]
                    df = df.set_index("date")
                    res = df.resample(f'{timeStep}us', label='right')

                    prev_y = None
                    prev_x = None
                    prev_ts = None
                    item_count = len(res) - 1
                    i = 0
                    for x, y in res:
                        x2 = (x, current_ts)[i == item_count]
                        i += 1

                        y = y.dropna().astype(int)
                        last_ts = int((x2 - t.start_ts).total_seconds() * t.microsec)
                        if not len(y.index):
                            if prev_y is None:
                                continue
                            y = pd.DataFrame({"code": prev_y, "ts": prev_ts}, index=[prev_x])

                        last_y = y.iat[-1, 0]
                        if prev_x:
                            y = pd.concat([y, pd.DataFrame({"code": prev_y, "ts": prev_ts}, index=[prev_x])])
                        y = pd.concat([y, pd.DataFrame({"code": last_y, "ts": last_ts}, index=[x])])
                        prev_x = x
                        prev_y = last_y
                        prev_ts = last_ts
                        y.sort_index(inplace=True)

                        y['duration'] = y['ts'].diff(periods=-1).fillna(0)
                        y['duration'] = (y['duration'] * (-1)).astype(int)
                        y = y.groupby('code')['duration'].sum()
                        y = y.astype(int)
                        value = y.to_dict()

                        for state in codes:
                            value.setdefault(state, 0)

                        if format_ts:
                            last_ts = t.int_to_local_timestamp(last_ts)
                        final_data.append((value, x, None))

                final_res['data'].append({
                    "tagId": tag["tagId"],
                    "data": final_data
                })

        return final_res

settings = DatafuncAppAPISettings()

app = TagsAppAPIDatafunc(settings=settings, title="`TagsAppAPIDatafunc` service")

router = APIRouter(prefix=f"{settings.api_version}/datafunc")

@router.get("/", response_model=dict | None, status_code=200)
async def data_get(q: str | None = None, payload: DataGet | None = None):
    if q:
        p = DataGet.model_validate_json(q)
    elif payload:
        p = payload
    else:
        return None
    res = await app.data_get(p)
    return res

app.include_router(router, tags=["datafunc"])
