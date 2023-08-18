"""
Модуль содержит классы, описывающие входные данные для команд CRUD для тегов
и класс сервиса ``tags_api_crud_svc``.
"""
import sys
import copy
from ldap.dn import str2dn, dn2str

sys.path.append(".")

from src.common import svc
from src.services.methods.app.methods_app_settings import MethodsAppSettings

class MethodsApp(svc.Svc):
    """Сервис работы с методами.

    Формат ожидаемых сообщений

    """

    _outgoing_commands = {}

    def __init__(self, settings: MethodsAppSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    def _set_incoming_commands(self) -> dict:
        return {
            "tags.uploadData": self._tag_changed
        }

    async def _tag_changed(self, mes: dict) -> dict:

        self._logger.debug(f"Run methods. Data: {mes}")

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

    async def _read_methods(self) -> None:
        # пока работаем только с вычислительными методами для тегов!
        # prsEntityTypeCode = 0
        get_methods = {
            "filter": {
                "objectClass": ["prsMethod"],
                "prsActive": True,
                "prsEntityTypeCode": 0
            },
            "attributes": ["cn"]
        }
        methods = await self._hierarchy.search(get_methods)
        for method in methods:
            initiatedBy_nodes = self._hierarchy.search(
                {
                    "base": f"cn=initiatedBy,cn=system,{method[1]}",
                    "filter": {
                        "cn": ['*']
                    },
                    "attributes": ["cn"]
                })

            for initiatedBy_id in initiatedBy_nodes:
                await self._amqp_consume["queue"].bind(
                    exchange=self._amqp_consume["exchanges"]["main"]["exchange"],
                    routing_key=initiatedBy_id
                )

            self._logger.debug(f"Метод {method[0]} прочитан.")

    async def on_startup(self) -> None:
        await super().on_startup()
        try:
            await self._read_methods()
        except Exception as ex:
            self._logger.error(f"Ошибка чтения методов: {ex}")

settings = MethodsAppSettings()

app = MethodsApp(settings=settings, title="`MethodsApp` service")
