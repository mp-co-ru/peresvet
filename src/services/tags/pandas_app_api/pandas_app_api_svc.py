"""
Модуль содержит классы, описывающие входные данные для команд CRUD для тегов
и класс сервиса ``tags_api_crud_svc``\.
"""
import sys
from typing import Any, List, NamedTuple
from typing_extensions import Annotated
from pydantic import (
    BaseModel, Field, field_validator,
    validator, BeforeValidator, ValidationError, ConfigDict
)

import pandas as pd

from fastapi import APIRouter

sys.path.append(".")

from src.common import svc
from src.common.api_crud_svc import valid_uuid
from src.services.tags.pandas_app_api.pandas_app_api_settings import PandasAppAPISettings
import src.common.times as t
from src.services.tags.app_api.tags_app_api_svc import TagsAppAPI, DataGet

class TagsAppAPIPandas(TagsAppAPI):

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
        if payload.format:
            # если изначальный запрос с флагом format = true,
            # то удалим его и отформатируем время уже в конце
            final_ts = t.int_to_local_timestamp(final_ts)
            payload.format = False

        res = await super().data_get(payload=payload)
        final_res = {
            "data": []
        }
        for tag in res["data"]:
            df = pd.DataFrame(tag["data"], columns=['code', 'ts', 'q'])
            df = df.drop('q', axis=1)
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

        return final_res

settings = PandasAppAPISettings()

app = TagsAppAPIPandas(settings=settings, title="`TagsAppAPIPandas` service")

router = APIRouter(prefix=f"{settings.api_version}/pandas")

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

app.include_router(router, tags=["pandas"])
