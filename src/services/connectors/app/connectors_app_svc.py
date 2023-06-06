from fastapi import WebSocket, WebSocketDisconnect, APIRouter, HTTPException
import sys


sys.path.append(".")

from src.common import base_svc
from connectors_app_settings import ConnectorsAppSettings
import json
import asyncio


class ConnectorApp(base_svc.BaseSvc):
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
