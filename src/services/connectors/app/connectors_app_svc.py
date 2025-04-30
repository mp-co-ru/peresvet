import sys
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
sys.path.append(".")

from src.services.connectors.app.connectors_app_settings import ConnectorsAppSettings
from src.common.app_svc import AppSvc
from src.common import hierarchy
import src.common.times as t

class ConnectorsApp(AppSvc):
    """Сервис работы с коннекторами.

    Подписывается на очередь ``connectors_tags_api`` обменника ``connectors_api_crud``,
    в которую публикует сообщения сервис ``connectors_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: ConnectorsAppSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

        self.linked_connectors = {}

    async def _deleted(self, mes: dict, routing_key: str = None):
        # удаление коннектора из модели:
        # если есть активное соединение с коннектором, разрываем его
        conn_id = mes["id"]
        if conn_id in self.linked_connectors.keys():
            await self.linked_connectors[conn_id].close()

    async def get_connector_tag_data(self, connector_id: str) -> dict:

        connector_data = await self._hierarchy.search(
            payload={
                "id": connector_id,
                "attributes": [
                    "prsActive", "prsJsonConfigString"
                ]
            }
        )
        if not connector_data:
            self._logger.info(f"{self._config.svc_name} :: Нет данных по коннектору {connector_id}")
            return {}

        res = {
            "connector": {
                "prsActive": connector_data[0][2]["prsActive"][0] == 'TRUE',
                "prsJsonConfigString": json.loads(
                    connector_data[0][2]["prsJsonConfigString"][0]
                )
            },
            "tags": []
        }

        tags = await self._hierarchy.search(payload={
            "base": connector_id,
            "scope": hierarchy.CN_SCOPE_SUBTREE,
            "filter": {
                "objectClass": ["prsConnectorTagData"]
            },
            "attributes": [
                "cn", "prsJsonConfigString"
            ]
        })

        for _, _, attributes in tags:
            tag = await self._hierarchy.search(payload={
                "id": attributes['cn'][0],
                "attributes": ["prsActive", "prsValueTypeCode"]
            })
            _, _, tag_attr = tag[0]
            if tag_attr["prsActive"][0] == 'TRUE':
                prs_value_type_code = int(tag_attr.get('prsValueTypeCode')[0])

                res["tags"].append({
                    "tagId": attributes['cn'][0],
                    "attributes": {
                        "prsJsonConfigString": json.loads(attributes["prsJsonConfigString"][0]),
                        "prsValueTypeCode": prs_value_type_code
                    }
                })

        return res

settings = ConnectorsAppSettings()

app = ConnectorsApp(settings=settings, title="ConnectorsApp")

router = APIRouter(prefix=f"{settings.api_version}/connectors")

@router.websocket("/{connector_id}")
async def get_req(websocket: WebSocket, connector_id: str):

    # если нет коннектора с указанным id или он неактивен, то выходим
    payload = {
        "id": connector_id,
        "attributes": ["prsActive"]
    }
    res = await app._hierarchy.search(payload=payload)
    if not res:
        app._logger.error(f"Запрос связи от коннектора '{connector_id}', но он не найден в модели.")
        return
    if res[0][2]["prsActive"][0] != 'TRUE':
        app._logger.error(f"Запрос связи от коннектора '{connector_id}'. Коннектор неактивен.")
        return

    await websocket.accept()

    app.linked_connectors[connector_id] = websocket

    try:
        app._logger.info(f"Установлена ws-связь с коннектором: {connector_id}")

        await websocket.receive_text()
        connector_tag_data = await app.get_connector_tag_data(connector_id=connector_id)
        await websocket.send_json(connector_tag_data)

        while True:
            tags_data_json = await websocket.receive_json()
            app._logger.info(f'{app._config.svc_name}: данные от коннектора {connector_id}: {tags_data_json}')
            res = await app._post_message(mes=tags_data_json, reply=False, routing_key="prsTag.app_api.data_set.*")
            if res is None:
                app._logger.error("Нет обработчика для команды записи данных.")

    except WebSocketDisconnect as e:

        try:
            app.linked_connectors.pop(connector_id)

            app._logger.error(f"Разрыв связи с коннектором {connector_id}. Ошибка: {e}")
            now_ts = t.now_int()
            data = {"data": []}
            for tag in connector_tag_data["tags"]:
                tag_data = {"tagId": tag["tagId"], "data": [[None, now_ts, None]]}
                data["data"].append(tag_data)
            res = await app._post_message(mes = data, routing_key="prsTag.app_api.data_set.*", reply=False)
            if res is None:
                app._logger.error("Нет обработчика для команды записи данных.")
        except:
            pass

app.include_router(router, tags=["connectors_app"])
