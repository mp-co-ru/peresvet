import sys
import copy
import aio_pika
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

sys.path.append(".")

from src.services.connectors.app.connectors_app_settings import ConnectorsAppSettings
from src.common import svc, hierarchy

class ConnectorApp(svc.Svc):

    """Сервис работы с коннекторами в платформе.
    """
    # def compile_json():
        
    pass

settings = ConnectorsAppSettings()
app = ConnectorApp(settings=settings, title="ConnectorsApp` service")
router = APIRouter()

@router.websocket("/ws")
async def send_connector_config(websocket: WebSocket, connector_id: str):
    await websocket.accept()
    app._logger.info("Установлена связь с коннектором {}".format(connector_id))
    while True:
        await websocket.send_text("Test")
        await websocket.close()
        raise WebSocketDisconnect()            
