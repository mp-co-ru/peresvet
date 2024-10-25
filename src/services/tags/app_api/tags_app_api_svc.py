"""
Запись и получение исторических данных.

Подробно работа с историческими данными и примеры использования ключей в запросе 
рассмотрены в разделе :ref:`historical_data`.
"""
import sys
import json
from typing import Any, List, NamedTuple
from typing_extensions import Annotated
from pydantic import (
    BaseModel, Field,
    validator, BeforeValidator, ConfigDict
)

from fastapi import APIRouter, Depends

sys.path.append(".")

from src.common.base_svc import BaseSvc
from src.common.api_crud_svc import valid_uuid, ErrorHandler
from src.services.tags.app_api.tags_app_api_settings import TagsAppAPISettings
import src.common.times as t

class DataPointItem(NamedTuple):
    y: float | dict | str | list | int | None = None
    x: int | str | None = None
    q: int | None = None

def x_must_be_int(v):
    match len(v):
        case 0:
            return DataPointItem(None, t.ts(None), None)
        case 1:
            return DataPointItem(v[0], t.ts(None), None)
        case 2:
            return DataPointItem(v[0], t.ts(v[1]), None)
        case 3:
            return DataPointItem(v[0], t.ts(v[1]), v[2])

    return v

class TagData(BaseModel):
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

    tagId: str = Field(
        title="id тега"
    )
    data: List[Annotated[DataPointItem, BeforeValidator(x_must_be_int)]]

    validate_id = validator('tagId', allow_reuse=True)(valid_uuid)
class AllData(BaseModel):
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

    data: List[TagData] = Field(
        title="Данные"
    )
class DataGet(BaseModel):
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

    tagId: str | list[str] = Field(
        title="Id или список id тегов"
    )
    start: int | str = Field(
        None,
        title="Метка времени начала периода."
    )
    finish: int | str = Field(
        default_factory=t.now_int,
        title="Метка времени окончания периода."
    )
    maxCount: int = Field(
        None,
        title="Максимальное количество точек в ответе."
    )
    format: bool = Field(
        False,
        title="Флаг форматирования меток времени в строку формата ISO8601"
    )
    actual: bool = Field(
        False,
        title="Флаг возврата только реально записанных данных."
    )
    value: Any = Field(
        None,
        title="Фильтр по значению"
    )
    count: int = Field(
        None,
        title="Количество запрашиваемых точек."
    )
    timeStep: int = Field(
        None,
        title="Шаг между соседними значениями."
    )

    @validator('tagId')
    @classmethod
    def tagId_list(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [v]
        else:
            return v

    @validator('finish')
    @classmethod
    def finish_in_iso_format(cls, v: Any) -> int:
        # если finish в виде строки, то строка должна быть в формате ISO8601
        try:
            return t.ts(v)
        except ValueError as ex:
            raise ValueError(
                (
                    "Метка времени должна быть строкой в формате ISO8601, "
                    "целым числом или отсутствовать."
                )
            )

    @validator('start')
    @classmethod
    def start_in_iso_format(cls, v: Any) -> int:
        if v is None:
            return
        # если finish в виде строки, то строка должна быть в формате ISO8601
        try:
            return t.ts(v)
        except ValueError as ex:
            raise ValueError(
                (
                    "Метка времени должна быть строкой в формате ISO8601, "
                    "целым числом или отсутствовать."
                )
            )

    validate_id = validator('tagId', allow_reuse=True)(valid_uuid)
class TagsAppAPI(BaseSvc):
    """Сервис работы с тегами в иерархии.

    Подписывается на очередь ``tags_api_crud`` обменника ``tags_api_crud``\,
    в которую публикует сообщения сервис ``tags_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: TagsAppAPISettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    def _set_handlers(self):
        self._handlers = {
            f"{self._config.hierarchy['class']}.app_api_client.data_get.*": self.data_get,
            f"{self._config.hierarchy['class']}.app_api_client.data_set.*": self.data_set
        }

    async def data_get(self, mes: DataGet, routing_key: str = None) -> dict:
        new_payload = mes
        if isinstance(mes, dict):
            new_payload = DataGet(**mes)

        body = new_payload.model_dump()

        res = await self._post_message(
            mes=body, reply=True, routing_key=f"{self._config.hierarchy['class']}.app_api.data_get.*"
        )
        # нет подписчика
        if res is None:
            res = {"error": {"code": 424, "message": f"Нет обработчика для команды чтения данных."}}
            return res

        if new_payload.format:
            final_res = {
                "data": []
            }

            for tag_item in res["data"]:
                new_tag_item = {
                    "tagId": tag_item["tagId"],
                    "data": []
                }
                for data_item in tag_item["data"]:
                    new_tag_item["data"].append((
                        data_item[0],
                        t.int_to_local_timestamp(data_item[1]),
                        data_item[2]
                    ))
                final_res["data"].append(new_tag_item)

            return final_res

        return res

    async def data_set(self, mes: dict | AllData, routing_key: str = None, error_handler: ErrorHandler = Depends()) -> None:
        try:
            if isinstance(mes, dict):
                s = json.dumps(mes)
                p = AllData.model_validate_json(s)
            else:
                p = mes
                
        except Exception as ex:
            res = {"error": {"code": 422, "message": f"Несоответствие входных данных: {ex}"}}
            app._logger.exception(res)
            await error_handler.handle_error(res)

        body = p.model_dump()
        
        res = await self._post_message(mes=body, reply=False, routing_key = f"{self._config.hierarchy['class']}.app_api.data_set.*")
        # нет подписчика
        if res is None:
            res = {"error": {"code": 424, "message": f"Нет обработчика для команды записи данных."}}
            #app._logger.error(res)
        return {}

settings = TagsAppAPISettings()

app = TagsAppAPI(settings=settings, title="`TagsAppAPI` service")

router = APIRouter(prefix=f"{settings.api_version}/data")

@router.get("/", response_model=dict | None, status_code=200)
async def data_get(q: str | None = None, payload: DataGet | None = None, error_handler: ErrorHandler = Depends()):
    """
    Запрос исторических данных.

    **Пример запроса в формате JSON.**

    .. http:example::
       :request: ../../../../docs/source/samples/data/getDataIn.txt
       :response: ../../../../docs/source/samples/data/getDataOut.txt

    **Пример query запроса.**

    .. http:example::
       :request: ../../../../docs/source/samples/data/getDataIn_query.txt
       :response: ../../../../docs/source/samples/data/getDataOut.txt

    **Параметры запроса:**

       * **tagId** (str | [str]): тег или список тегов, по которым запрашиваются данные;
       * **format** (bool): флаг перевода меток времени в ответе в формат ISO8601;
       * **actual** (bool): если = true, то возвращаются только реально записанные в базу данные,
         без интерполируемых значений на границах диапазона;
       * **count** (int): количество значений тега, которое необходимо возвратить;
       * **start** (int | str): начало запрашиваемого периода;
       * **finish** (int | str): окончание запрашиваемого периода;
       * **timeStep** (int): шаг в микросекундах между соседними возвращаемыми значениями тега;
       * **maxCount** (int): максимальное количество значений одного тега в ответе на запрос;
       * **value** (any): фильтр на значения тега.

    **Ответ:**

        * **data** (list) - возвращаемые данные;
        * **detail** (str) - пояснение к возникшей ошибке.

    """
    if q:
        try:
            p = DataGet.model_validate_json(q)
        except ValueError as ex:
            res = {"error": {"code": 422, "message": f"Несоответствие входных данных: {ex}"}}
            await error_handler.handle_error(res)
    elif payload:
        p = payload
    else:
        return None
    res = await app.data_get(p)
    await error_handler.handle_error(res)
    return res

@router.post("/", status_code=200)
async def data_set(payload: AllData, error_handler: ErrorHandler = Depends()):
    """Запись исторических данных тега.

    .. http:example::
       :request: ../../../../docs/source/samples/data/addDataIn.txt
       :response: ../../../../docs/source/samples/data/addDataOut.txt

    **Параметры запроса:**

      * **data** ([json]) - массив данных тегов; каждый элемент этого массива - 
        json с данными одного тега. Json имеет формат:

        * **tagId** (str) - id тега;
        * **data** ([[value, timestamp, quality_code]]) - массив значений тега; каждое значение - 
          массив из трёх элементов: значение тега, метка времени (целое число микросекунд или
          строка в формате ISO8601). В случае отсутствия метки времени берётся текущий момент времени.
          В случае отсутствия кода качества берётся значение ``null``, означающее нормальное качество.

    **Ответ:**

      null

    """
    res = await app.data_set(payload)
    await error_handler.handle_error(res)
    return res

'''
@router.websocket("/ws/data")
async def websocket_endpoint(websocket: WebSocket):

    try:
        await websocket.accept()
        app._logger.debug(f"Установлена ws-связь.")

        while True:
            try:
                received_data = await websocket.receive_json()
                action = received_data.get("action")
                if not action:
                    raise ValueError("Не указано действие в команде.")
                data = received_data.get("data")
                if not data:
                    raise ValueError("Не указаны данные команды.")

                match action:
                    case "get":
                        res = await app.data_get(DataGet(**data))
                    case "set":
                        await app.data_set(AllData(**data))
                        res = {
                            "error": {"id": 0}
                        }
                await websocket.send_json(res)

            except TypeError as ex:
                app._logger.error(f"Неверный формат данных: {ex}")
            except ValidationError as ex:
                app._logger.error(f"Неверные данные сообщения: {ex}")
            except json.JSONDecodeError as ex:
                app._logger.error(f"Сообщение должно быть в виде json: {ex}")
            except ValueError as ex:
                app._logger.error(ex)

    except Exception as ex:
        app._logger.error(f"Разрыв ws-связи: {ex}")
'''

app.include_router(router, tags=["data"])
