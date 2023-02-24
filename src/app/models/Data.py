from typing import List, Any, Union
from pydantic import BaseModel, Field, validator

import app.times as t

class PrsDataItem(BaseModel):
    """
    Класс для атомарного значения тега.
    """
    x: int | str = Field(None, title="Метка времени",
       description=(
            "Может быть либо целым числом, в этом случае это микросекунды, "
            "либо строкой в формате ISO8601."
       )
    )
    y: float | int | dict | str = Field(None, title="Значение тега")
    q: int = Field(None, title="Код качества")

class PrsTagSetData(BaseModel):
    tagId: str
    data: List[PrsDataItem]

class PrsReqSetData(BaseModel):
    """
    Запрос на запись данных
    """
    data: List[PrsTagSetData]

class PrsRespTagGetData(PrsTagSetData):
    excess: bool

class PrsRespGetData(BaseModel):
    data: List[PrsRespTagGetData]

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

<<<<<<< HEAD
    @validator('tagId', always=True)
=======
    @classmethod
    @validator('tagId')
>>>>>>> f3852a9c2e630cb5d84b72a31ccbfcd2ae531049
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
