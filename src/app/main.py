import json
import asyncio

from fastapi import WebSocket, WebSocketDisconnect, status
from fastapi.exceptions import HTTPException, WebSocketException

from app.svc.Services import Services as svc
from app.PrsApplication import PrsApplication
import app.api.tags as tags
import app.api.dataStorages as dataStorages
import app.api.data as data
import app.api.connectors as connectors
from app.models.Data import PrsReqSetData, PrsReqGetData

#from fastapi_profiler import PyInstrumentProfilerMiddleware

app = PrsApplication(title='Peresvet')

app.include_router(tags.router, prefix="/tags", tags=["tags"])
app.include_router(dataStorages.router, prefix="/dataStorages", tags=["dataStorages"])
app.include_router(data.router, prefix="/data", tags=["data"])
app.include_router(connectors.router, prefix="/connectors", tags=["connectors"])

'''
app.add_middleware(
    PyInstrumentProfilerMiddleware,
    server_app=app,  # Required to output the profile on server shutdown
    profiler_output_type="html",
    is_print_each_request=False,  # Set to True to show request profile on
                                  # stdout on each request
    open_in_browser=False,  # Set to true to open your web-browser automatically
                            # when the server shuts down
    html_file_name="example_profile.html"  # Filename for output
)
'''

@app.on_event("startup")
async def startup_event():
    await app.set_data_storages()

#TODO:
# 1. вынести код работы с вебсокетом в отдельный файл, сделать по типу строк выше
# 2. разобраться с таймаутами пинг-понга. параметры в командной строке при запуске приложения не работают!

# /ws/{api}
# в качестве {api} передаётся имя группы команд: data/tags/dataStorages и т.д.
# далее в качестве тела запроса передаётся тот же json, который передаётся в
# соответствующей http-команде;
# этот json передаётся как значение ключа, имя которого - post/get/put/delete
# в случае группы команд connectors добавляется еще ключ connect
# значением которого является id коннектора
# пример:
# запрос на создание тэга:
# ws://<>/ws/tags/
# тело запроса:
# {
#   "post": {
#        "attributes": {
#            "cn": "tag_name"
#        }
#    }
# }
#
# запрос при соединении коннектора с платформой:
# ws://<>/connectors/
# тело запроса:
# {
#   "connect": "<some id>"
# }
@app.websocket("/ws/{api}")
async def websocket_endpoint(websocket: WebSocket, api: str):
    try:
        if not api in ['data', 'connectors']:
            er_str = f"Неподдерживаемая группа команд: {api}"
            svc.logger.error(er_str)
            raise WebSocketException(code=status.WS_1002_PROTOCOL_ERROR, reason=er_str)

        await svc.ws_pool.connect(websocket)

        svc.logger.debug(f"Установлена ws-связь. API: {api}")

        while True:
            received_data = await websocket.receive_json()
            if api == 'connectors':
                connector_id = received_data.get["connect"]
                if connector_id:
                    response = {}
                    try:
                        response = app.response_to_connector(connector_id)
                    except HTTPException as ex:
                        er_str = f"Ошибка при установлении связи с коннектором {connector_id}: {ex}"
                        svc.logger.error(er_str)
                        await websocket.send_text(er_str)
                        await websocket.close()
                        raise WebSocketDisconnect() from ex

                    await websocket.send_json(response)

            else:
                for command, data_body in received_data.items():
                    # TODO: проверить формирование нужных классов из данных
                    if command == "post":
                        res = await app.data_set(data=PrsReqSetData(**data_body))
                        await websocket.send_json({"status_code": res.status_code})
                    elif command == "get":
                        res = await app.data_get(data=PrsReqGetData(**data_body))
                        await websocket.send_json(res)

    except Exception as ex:
        svc.ws_pool.disconnect(websocket)
        svc.logger.info(f"Разрыв связи с коннектором {connector_id}: {ex}")


@app.on_event("startup")
async def startup():
    pass

@app.on_event("shutdown")
async def shutdown():
    pass
