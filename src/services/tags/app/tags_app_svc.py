"""
Модуль содержит классы, описывающие входные данные для команд CRUD для тегов
и класс сервиса ``tags_api_crud_svc``.
"""
import sys
import copy

sys.path.append(".")

from src.common import svc
from src.services.tags.app.tags_app_settings import TagsAppSettings

class TagsApp(svc.Svc):
    """Сервис работы с тегами.

    Подписывается на очередь ``tags_app_api`` обменника ``peresvet``,
    в которую публикует сообщения сервис ``tags_app_api`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    _outgoing_commands = {}

    def __init__(self, settings: TagsAppSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    def _set_incoming_commands(self) -> dict:
        return {
            "tags.setData": self._data_set,
            "tags.getData": self._data_get
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

        mes["action"] = "tags.uploadData"

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

settings = TagsAppSettings()

app = TagsApp(settings=settings, title="`TagsApp` service")
