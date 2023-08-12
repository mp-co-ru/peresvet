"""
Модуль содержит классы, описывающие входные данные для команд CRUD для тегов
и класс сервиса ``tags_api_crud_svc``.
"""
import sys
import asyncio
import copy
from uuid import UUID
from typing import Any, List
from pydantic import BaseModel, Field, validator

from fastapi import APIRouter

sys.path.append(".")

from src.common import svc
import src.common.times as t
from src.services.alerts.app.alerts_app_settings import AlertsAppSettings

class AlertsApp(svc.Svc):
    """Сервис работы с тревогами.
    """

    _outgoing_commands = {}

    def __init__(self, settings: AlertsAppSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    def _set_incoming_commands(self) -> dict:
        return {
            "alerts.getAlarms": self._data_set,
            "alerts.ackAlarms": self._data_get
        }

    async def _data_get(self, mes: dict) -> dict:

        self._logger.debug(f"Data get mes: {mes}")

        new_payload = copy.deepcopy(mes["data"])
        tag_ids = new_payload.pop("tagId")
        final_res = {
            "data": []
        }
        for tag_id in tag_ids:

            new_payload["tagId"] = [tag_id]

            self._logger.debug((
                f"Creating new task. payload: {new_payload}"
            ))

            res = await self._post_message({
                    "action": "tags.downloadData",
                    "data": new_payload
                },
                reply=True,
                routing_key=tag_id
            )
            final_res["data"] += res["data"]

        return final_res

    async def _data_set(self, mes: dict) -> None:

        for tag_item in mes["data"]["data"]:

            await self._post_message({
                    "action": "tags.uploadData",
                    "data": {
                        "data": [
                            tag_item
                        ]
                    }
                },
                reply=False,
                routing_key=tag_item["tagId"]
            )

settings = AlertsAppSettings()

app = AlertsApp(settings=settings, title="`TagsApp` service")
