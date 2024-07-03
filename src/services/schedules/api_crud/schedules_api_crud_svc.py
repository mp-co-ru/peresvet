"""
Модуль содержит примеры запросов и ответов на них, параметров которые могут входить в
запрос, в сервисе schedules.
"""
import sys
import json
from typing import Any, List
from pydantic import Field, validator

from fastapi import APIRouter

sys.path.append(".")

from src.common import api_crud_svc as svc
from src.common import times as t
from src.services.schedules.api_crud.schedules_api_crud_settings import SchedulesAPICRUDSettings

class ScheduleCreateAttributes(svc.NodeAttributes):
    @validator('prsJsonConfigString')
    @classmethod
    def config_str(cls, v: str) -> str:

        def raise_exception():
            raise ValueError(
                'prsJsonConfigString должен быть вида '
                '{'
                '   "start": "<дата ISO8601>", '
                '   "end": "<дата ISO8601>", '
                '   "interval_type": "seconds | minutes | hours | days", '
                '   "interval_value": <int> '
                '} '
                'Параметр "end" - необязательный.'
            )

        if not v:
            raise_exception()

        try:
            config = json.loads()
            start = config.get("start")
            end = config.get("end")
            interval_type = config.get("interval_type")
            interval_value = config.get("interval_value")

            if not start or not interval_type or not interval_value:
                raise_exception()

            start = t.ts(start)
            if end:
                end = t.ts(end)
            if interval_type not in ("seconds", "minutes", "hours", "days"):
                raise_exception()
            if not isinstance(interval_value, int):
                raise_exception()
            if interval_value < 1:
                raise_exception()

        except json.JSONDecodeError as ex:
            raise_exception()

        return v

class ScheduleCreate(svc.NodeCreate):
    attributes: ScheduleCreateAttributes = Field(title="Атрибуты узла")

    # validate_id = validator('parentId', 'dataStorageId', 'connectorId', allow_reuse=True)(svc.valid_uuid)

class ScheduleRead(svc.NodeRead):
    pass

class OneScheduleInReadResult(svc.OneNodeInReadResult):
    pass

class ScheduleReadResult(svc.NodeReadResult):
    data: List[OneScheduleInReadResult] = Field(title="Список расписаний.")
    pass

class ScheduleUpdate(svc.NodeUpdate):
    pass

class SchedulesAPICRUD(svc.APICRUDSvc):
    """Сервис работы с расписаниями в иерархии.

    Подписывается на очередь ``schedules_api_crud`` обменника ``schedules_api_crud``\,
    в которую публикует сообщения сервис ``schedules_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    _outgoing_commands = {
        "create": "schedules.create",
        "read": "schedules.read",
        "update": "schedules.update",
        "delete": "schedules.delete"
    }

    def __init__(self, settings: SchedulesAPICRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def create(self, payload: ScheduleCreate) -> dict:
        return await super().create(payload=payload)

    async def read(self, payload: ScheduleRead) -> dict:
        return await super().read(payload=payload)

    async def update(self, payload: ScheduleUpdate) -> dict:
        return await super().update(payload=payload)

settings = SchedulesAPICRUDSettings()

app = SchedulesAPICRUD(settings=settings, title="`SchedulesAPICRUD` service")

router = APIRouter(prefix=f"{settings.api_version}/schedules")

@router.post("/", response_model=svc.NodeCreateResult, status_code=201)
async def create(payload: ScheduleCreate):
    """
    Метод добавляет расписание в иерархию.

    **Request**:

        .. http:example::
            :request: ../../../../docs/source/samples/schedules/addScheduleIn.txt
            :response: ../../../../docs/source/samples/schedules/addScheduleOut.txt

        * **attributes** (dict) - словарь с параметрами для создания расписания.

          * **cn** (str) - имя расписания; Необязательный атрибут;
          * **description** (str) - описание экземпляра. Необязательный атрибут;
          * **prsJsonConfigString** (str) - Строка содержит, в случае необходимости,
            конфигурацию узла. Интерпретируется сервисом, управляющим сущностью,
            которой принадлежит экземпляр. Необязательный аттрибут
          * **prsActive** (bool) - Определяет, активен ли экземпляр. Необязательный атрибут;
          * **prsDefault** (bool) - Если = ``True``, то данный экземпляр. Необязательный атрибут;
            считается узлом по умолчанию в списке равноправных узлов данного уровня иерархии.
            Необязательный атрибут.
          * **prsIndex** (int) - Если у узлов одного уровня иерархии проставлены индексы, то
            перед отдачей клиенту списка экземпляров они сортируются
            в соответствии с их индексами. Необязательный атрибут
          * **prsArchive** (bool) - Флаг архивирования начений тега. Необязательный аттрибут
          * **prsCompress** (bool) - Флаг сжатия значений тега. Необязательный атрибут;
            Если не указан, то поиск ведётся от главного узла иерархии. Необязательный атрибут;
          * **prsMaxLineDev** (float) - Параметр сжатия значений тега. Необязательный атрибут;
          * **prsStep** (bool) - Флаг `ступенчатого тега`. Необязательный атрибут;
          * **prsUpdate** (bool) - Флаг обновления значений тега. Необязательный атрибут;
          * **prsValueTypeCode** (int) - Тип значений тега. Необязательный атрибут;
          * **prsDefaultValue** (Any) - Значение тега по умолчанию. Необязательный атрибут;
          * **prsMeasureUnits** (str) - Единицы измерения тега. Необязательный атрибут;


    **Response**:

        * **id** (uuid) - id созданного тега
        * **detail** (str) - пояснения к ошибке

    """
    return await app.create(payload)

@router.get("/", response_model=svc.NodeReadResult | None, status_code=200)
async def read(q: str | None = None, payload: ScheduleRead | None = None):
    return await app.api_get_read(ScheduleRead, q, payload)

@router.put("/", status_code=202)
async def update(payload: ScheduleUpdate):
    await app.update(payload)

@router.delete("/", status_code=202)
async def delete(payload: ScheduleRead):
    await app.delete(payload)

app.include_router(router, tags=["schedules"])
