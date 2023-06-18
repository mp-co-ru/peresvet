import sys
import copy
import json
from ldap.dn import str2dn, dn2str

sys.path.append(".")

from dataStorages_model_crud_settings import DataStoragesModelCRUDSettings
from src.common import model_crud_svc
from src.common import hierarchy

class DataStoragesModelCRUD(model_crud_svc.ModelCRUDSvc):
    """Сервис работы с хранилищами данных в иерархии.

    Подписывается на очередь ``dataStorages_api_crud`` обменника ``dataStorages_api_crud``,
    в которую публикует сообщения сервис ``dataStorages_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: DataStoragesModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def _reading(self, mes: dict) -> dict:
        pass

    async def _get_routing_key_for_datastorage(self, ds_id: str) -> str:
        """Метод возвращает routing_key для определённого хранилища данных.

        Args:
            ds_id (str): id хранилища данных.

        Returns:
            str: _description_
        """
        item = await anext(self._hierarchy.search({
            "id": [ds_id],
            "attributes": ["prsJsonConfigString"]
        }))

        return json.loads(item[2]["prsJsonConfigString"][0])["routing_key"]

    async def _unlink_tag(self, tag_id: str) -> None:
        """Метод отвязки тега от хранилища.
        Ищем, к какому хранилищу привязан тег и посылаем этому хранилищу
        сообщение об отвязке, после удаляем ссылку на тег.

        Args:
            tag_id (str): id отвязываемого тега
        """
        item = await anext(self._hierarchy.search({
            "base": self._config.hierarchy["node_id"],
            "scope": hierarchy.CN_SCOPE_SUBTREE,
            "filter": f"&(cn={tag_id})(objectClass=prsDatastorageTagData)",
            "attributes": ["cn"]
        }))
        if not item[0]:
            self._logger.info(
                f"Тег {tag_id} не привязан ни к одному хранилищу."
            )
            return

        datastorage_id = await self._hierarchy.get_node_id(
            dn2str(str2dn(item[1])[2:])
        )

        routing_key = self._get_routing_key_for_datastorage(datastorage_id)

        await self._post_message(mes={"action": "unlinkTag", "id": [tag_id]},
            routing_key=routing_key)

        await self._hierarchy.delete(item[0])

        self._logger.info(
            f"Послано сообщение об отвязке тега {tag_id} "
            f"от хранилища {datastorage_id}"
        )

    async def _link_tag(self, payload: dict, datastorage_id: str = None) -> None:
        """Метод привязки тега к хранилищу.

        Логика работы метода: предполагаем, что тег может быть привязан только
        к одному хранилищу (может, есть смысл в привязке тега сразу к
        нескольким хранилищам, чтобы данные писались одновременно в разные
        хранилища; только тут возникает вопрос: при чтении данных, из
        какого хранилища эти данные брать).

        Если тег уже привязан к какому-либо хранилищу (ищем ссылку на этот тег
        в иерархии ``cn=dataStorages,cn=prs``), то сначала отвязываем тег от
        предыдущего хранилища, затем привязываем к новому.

        Args:
            payload (dict): {
                "id": "tag_id",
                "attributes": {
                    "prsStore":
                }
            }
        """
        await self._unlink_tag(payload["id"])

        routing_key = await self._get_routing_key_for_datastorage(datastorage_id)

        # res = {
        #   "prsStore": {...}
        # }
        res = await self._post_message(
            mes={"action": "linkTag", "data": payload},
            reply=self._amqp_callback_queue.name,
            routing_key=routing_key)

        prs_store = res.get("prsStore")
        tags_node_id = await self._hierarchy.get_node_id(
            f"cn=tags,cn=system,{self._hierarchy.get_node_dn(datastorage_id)}"
        )
        new_node_id = await self._hierarchy.add(
            base=tags_node_id,
            attribute_values={
                "objectCalss": ["prsDatastorageTagData"],
                "cn": payload["id"],
                "prsStore": prs_store
            }
        )
        await self._hierarchy.add_alias(
            parent_id=new_node_id,
            aliased_object_id=payload["id"],
            alias_name=payload["id"]
        )

        self._logger.info(
            f"Тег {payload['id']} привязан к хранилищу {datastorage_id}"
        )



    async def _link_alert(payload: dict) -> None:
        pass



    async def _creating(self, mes: dict, new_id: str) -> None:
        sys_id = await anext(self._hierarchy.search({
            "base": new_id,
            "scope": hierarchy.CN_SCOPE_ONELEVEL,
            "filter": {
                "cn": ["system"]
            }
        }))

        sys_id = sys_id[0]

        await self._hierarchy.add(sys_id, {"cn": "tags"})
        await self._hierarchy.add(sys_id, {"cn": "alerts"})

        for item in mes["data"]["linkTags"]:
            await self._link_tag(item, new_id)
        for item in mes["data"]["linkAlerts"]:
            await self._link_alert(item, new_id)

settings = DataStoragesModelCRUDSettings()

app = DataStoragesModelCRUD(settings=settings, title="DataStoragesModelCRUD")
