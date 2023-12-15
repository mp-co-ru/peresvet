import sys
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
sys.path.append(".")

from src.services.connectors.app.connectors_app_settings import ConnectorsAppSettings
from src.common import svc, hierarchy

class ConnectorsApp(svc.Svc):
    """Сервис работы с коннекторами.

    Подписывается на очередь ``connectors_tags_api`` обменника ``connectors_api_crud``,
    в которую публикует сообщения сервис ``connectors_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: ConnectorsAppSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)


        """{
    "prsJsonConfigString": "{...}",
    "tags": [
        {
            "tagId": "12",
            "attributes": {
                "prsMaxLineDev": 1,
                "prsValueScale": 1,
                "prsValueTypeCode": 1,
                "prsSource": {
                  "register": 1,
                  "span": 10,
                  "frequency": 1
                }
            }
        }
    ]
}

{
   "data": [
       {
            "tagId": "...",
            "data": [
                 {
                     "x": 1, 
                     "y": 2, 
                     "q": 100
                 }
            ]
       }
  ]
}

        """
    async def get_connector_tag_data(self, connector_id: str) -> dict:
        res = {
            "tags": []
        }

        tags = await self._hierarchy.search(payload={
            "base": connector_id,
            "scope": hierarchy.CN_SCOPE_SUBTREE,
            "filter": {
                "objectClass": ["prsConnectorTagData"]
            }
        })

        for id_, _, attributes in tags:
            tag = await self._hierarchy.search(payload={
                "scope": hierarchy.CN_SCOPE_SUBTREE,
                "id": attributes.get('cn')[0],
                "filter": {
                    "objectClass": ["prsTag"]
                }
            })
            tag_id, _, tag_attr = tag[0]
            prs_value_type_code = tag_attr.get('prsValueTypeCode')
            if prs_value_type_code:
                attributes['prsValueTypeCode'] = [0]
                if id_:
                    res["tags"].append({
                        "tagId": tag_id,
                        "attributes": attributes
                    })
        
        return res
        


settings = ConnectorsAppSettings()

app = ConnectorsApp(settings=settings, title="ConnectorsApp")

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

@router.websocket("/{connector_id}")
async def get_req(websocket: WebSocket, connector_id: str):

    # await manager.connect(websocket)
    await websocket.accept()
    try:
        app._logger.info(f"Установлена ws-связь с коннектором: {connector_id}")
    
        init_text = await websocket.receive_text()
        connector_tag_data = await app.get_connector_tag_data(connector_id=connector_id)
        await websocket.send_json(connector_tag_data)

        while True:
            tags_data_json = await websocket.receive_json()
            for tag_data in tags_data_json.get('data'):

                body = {
                        "action": "tags.setData",
                        "data": {"data": [tag_data]}
                        }
                await app._post_message(body, reply=False)
                app._logger.info(f'Данные коннектора {connector_id} отправлены')
            
    except WebSocketDisconnect as e:
        # manager.disconnect(websocket)
        app._logger.error(f"Разрыв связи с коннектором {connector_id}. Ошибка: {e}")


app.include_router(router, prefix=f"{settings.api_version}/connectors", tags=["connectors_app"])