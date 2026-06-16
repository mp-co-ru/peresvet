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
    field_validator, BeforeValidator, ConfigDict
)

from fastapi import APIRouter, Depends, Query
from starlette.requests import Request

sys.path.append(".")

from src.common.base_svc import BaseSvc
from src.common.api_crud_svc import valid_uuid, ErrorHandler
from src.common.authorization import authorize_action
from src.services.tags.app_api.tags_app_api_settings import TagsAppAPISettings
import src.common.times as t
from src.common.tag_data_points import normalize_point_xyq

class DataPointItem(NamedTuple):
    x: int | str | None = None
    y: float | dict | str | list | int | None = None
    q: int | None = None

def normalize_point(v):
    v2 = normalize_point_xyq(v)
    if isinstance(v2, tuple) and len(v2) == 3:
        return DataPointItem(v2[0], v2[1], v2[2])
    return v2

class TagData(BaseModel):
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

    tagId: str = Field(
        title="id тега"
    )
    data: List[Annotated[DataPointItem, BeforeValidator(normalize_point)]]
    params: dict[str, Any] | None = Field(
        None,
        title="Параметры операции для конкретного тега",
    )

    @field_validator("tagId")
    @classmethod
    def validate_id(cls, v: Any) -> Any:
        return valid_uuid(v)
class AllData(BaseModel):
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=(), extra="forbid")

    data: List[TagData] = Field(
        title="Данные"
    )
class DataGet(BaseModel):
    # https://giters.com/pydantic/pydantic/issues/6322
    # extra: произвольные query-параметры (например calendarTagId) для виртуальных методов → clientRequest
    model_config = ConfigDict(protected_namespaces=(), extra="allow")

    tagId: str | list[str] = Field(
        title="Id или список id тегов"
    )
    start: int | str | None = Field(
        None,
        title="Метка времени начала периода."
    )
    finish: int | str = Field(
        default_factory=t.now_int,
        title="Метка времени окончания периода."
    )
    maxCount: int | None = Field(
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
    count: int | None = Field(
        None,
        title="Количество запрашиваемых точек."
    )
    timeStep: int | None = Field(
        None,
        title="Шаг между соседними значениями."
    )
    params: dict[str, Any] | None = Field(
        None,
        title="Дополнительные параметры запроса."
    )
    evalContextTagId: str | None = Field(
        None,
        title="Служебное поле платформы: предотвращение повторного виртуального чтения при разборе параметров метода.",
    )

    @field_validator("tagId")
    @classmethod
    def tagId_list(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [v]
        else:
            return v

    @field_validator("finish")
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

    @field_validator("start")
    @classmethod
    def start_in_iso_format(cls, v: Any) -> int | None:
        if v is None:
            return None
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

    @field_validator("tagId")
    @classmethod
    def validate_id(cls, v: Any) -> Any:
        return valid_uuid(v)

    @field_validator("evalContextTagId")
    @classmethod
    def eval_context_tag_id(cls, v: Any) -> str | None:
        if v is None or v == "":
            return None
        return str(valid_uuid(str(v)))


_DATA_GET_QUERY_KNOWN_KEYS = frozenset(
    {
        "tagId",
        "start",
        "finish",
        "maxCount",
        "format",
        "actual",
        "value",
        "count",
        "timeStep",
        "params",
        "q",
    }
)
# Не принимать из произвольного query (внутреннее поле цепочки data_get).
_DATA_GET_QUERY_BLOCKED_KEYS = frozenset({"evalContextTagId"})


def _merge_extra_data_get_query_params(request: Request, body: dict) -> dict:
    """Проброс нестандартных query-параметров (не объявленных в сигнатуре GET) в тело DataGet."""
    out = dict(body)
    for key in request.query_params.keys():
        if key in _DATA_GET_QUERY_KNOWN_KEYS or key in _DATA_GET_QUERY_BLOCKED_KEYS:
            continue
        if key in out:
            continue
        out[key] = request.query_params.get(key)
    return out


def _data_get_apply_query_extras(request: Request, model: DataGet) -> DataGet:
    """Добавить к уже разобранному DataGet произвольные query-параметры (для путей ``q`` / ``payload``)."""
    d = model.model_dump()
    for key in request.query_params.keys():
        if key in _DATA_GET_QUERY_KNOWN_KEYS or key in _DATA_GET_QUERY_BLOCKED_KEYS:
            continue
        d[key] = request.query_params.get(key)
    return DataGet.model_validate(d)


class TagsAppAPI(BaseSvc):
    """Сервис работы с тегами в иерархии.

    Подписывается на очередь ``tags_api_crud`` обменника ``tags_api_crud``,
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

    async def data_get(self, mes: DataGet, routing_key: str | None = None) -> dict:
        new_payload = mes
        if isinstance(mes, dict):
            new_payload = DataGet(**mes)

        body = new_payload.model_dump()
        await authorize_action(
            f"{self._config.hierarchy['class']}.data_get",
            resource={"tagIds": body["tagId"]},
            payload=body,
        )

        res = await self._post_message(
            mes=body, reply=True, routing_key=f"{self._config.hierarchy['class']}.app_api.data_get.*"
        )
        # нет подписчика
        if res is None:
            res = {"error": {"code": 424, "message": f"Нет обработчика для команды чтения данных."}}
            return res
        if not isinstance(res, dict):
            return {"error": {"code": 500, "message": "Некорректный ответ обработчика data_get."}}

        if new_payload.format:
            if "error" in res or "data" not in res:
                return res

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
                        t.int_to_local_timestamp(data_item[0]),
                        data_item[1],
                        data_item[2]
                    ))
                final_res["data"].append(new_tag_item)

            return final_res

        return res

    async def data_set(self, mes: dict | AllData, routing_key: str | None = None, error_handler: ErrorHandler = Depends()) -> dict:

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
            return {}

        body = p.model_dump()
        await authorize_action(
            f"{self._config.hierarchy['class']}.data_set",
            resource={"tagIds": [item["tagId"] for item in body["data"]]},
            payload=body,
        )
        res = await self._post_message(mes=body, reply=True, routing_key = f"{self._config.hierarchy['class']}.app_api.data_set.*")
        # нет подписчика
        if res is None:
            res = {"error": {"code": 424, "message": f"Нет обработчика для команды записи данных."}}
            app._logger.error(res["error"]["message"])
            return res
        if not isinstance(res, dict):
            return {"error": {"code": 500, "message": "Некорректный ответ обработчика data_set."}}
        return res

settings = TagsAppAPISettings()

app = TagsAppAPI(settings=settings, title="`TagsAppAPI` service")

router = APIRouter(prefix=f"{settings.api_version}/data")

@router.get("/", response_model=dict | None, status_code=200)
async def data_get(
    request: Request,
    # основной (правильный) способ для GET: отдельные query-параметры
    tagId: list[str] | None = Query(None),
    start: str | None = None,
    finish: str | None = None,
    maxCount: int | None = None,
    format: bool = False,
    actual: bool = False,
    value: str | None = None,
    count: int | None = None,
    timeStep: int | None = None,
    params: str | None = None,
    # fallback для обратной совместимости
    q: str | None = None,
    payload: DataGet | None = None,
    error_handler: ErrorHandler = Depends(),
):
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
       * **params** (json): дополнительные параметры запроса (например
         ``allRecordsAsValue`` для интеграционных табличных тегов).
       * Любые другие query-параметры (например ``calendarTagId``) передаются в цепочку
         чтения данных и попадают в ``clientRequest`` виртуального метода для параметров
         с источником «данные из запроса клиента».

    **Ответ:**

        * **data** (list) - возвращаемые данные;
        * **detail** (str) - пояснение к возникшей ошибке.

    """
    if q:
        try:
            p = _data_get_apply_query_extras(request, DataGet.model_validate_json(q))
        except ValueError as ex:
            res = {"error": {"code": 422, "message": f"Несоответствие входных данных: {ex}"}}
            await error_handler.handle_error(res)
            return {}
    elif payload:
        p = _data_get_apply_query_extras(request, payload)
    else:
        if not tagId:
            return None
        try:
            parsed_value = None
            if value is not None:
                try:
                    parsed_value = json.loads(value)
                except Exception:
                    parsed_value = value

            body = {
                "tagId": tagId,
                "format": format,
                "actual": actual,
            }
            if start is not None:
                body["start"] = start
            if finish is not None:
                body["finish"] = finish
            if maxCount is not None:
                body["maxCount"] = maxCount
            if parsed_value is not None:
                body["value"] = parsed_value
            if count is not None:
                body["count"] = count
            if timeStep is not None:
                body["timeStep"] = timeStep
            if params is not None:
                body["params"] = json.loads(params)

            body = _merge_extra_data_get_query_params(request, body)
            p = DataGet.model_validate(body)
        except Exception as ex:
            res = {"error": {"code": 422, "message": f"Несоответствие входных данных: {ex}"}}
            await error_handler.handle_error(res)
            return {}
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
