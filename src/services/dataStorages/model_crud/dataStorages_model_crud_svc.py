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

    _outgoing_commands = {
        "created": "dataStorages.created",
        "mayUpdate": "dataStorages.mayUpdate",
        "updating": "dataStorages.updating",
        "updated": "dataStorages.updated",
        "mayDelete": "dataStorages.mayDelete",
        "deleting": "dataStorages.deleting",
        "deleted": "dataStorages.deleted"
    }

    def __init__(self, settings: DataStoragesModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    def _set_incoming_commands(self) -> dict:
        return {
            "dataStorages.create": self._create,
            "dataStorages.read": self._read,
            "dataStorages.update": self._update,
            "dataStorages.delete": self._delete,

            #TODO: этот блок надо доработать
            ".mayUpdate": self._may_update,
            ".updating": self._updating,
            ".mayDelete": self._may_delete,
            ".deleting": self._deleting
        }

    async def _further_read(self, mes: dict, search_result: dict) -> dict:
        res = {"data": []}
        for ds in search_result["data"]:
            ds_id = ds["id"]
            new_ds = copy.deepcopy(ds)
            if mes["getLinkedTags"]:
                new_ds["linkedTags"] = []
                items = await self._hierarchy.search(
                    {
                        "base": ds_id,
                        "filter": {
                            "objectClass": ["prsDatastorageTagData"]
                        },
                        "attributes": ["cn", "prsStore"]
                    }
                )
                if items:
                    new_ds["linkedTags"].append(
                        {
                            "id": items[0][0],
                            "attributes": {
                                "prsStore": items[0][2]["prsStore"][0]
                            }
                        }
                    )

            if mes["getLinkedAlerts"]:
                new_ds["linkedAlerts"] = []
                items = await self._hierarchy.search(
                    {
                        "base": ds_id,
                        "filter": {
                            "objectClass": ["prsDatastorageAlertData"]
                        },
                        "attributes": ["cn", "prsStore"]
                    }
                )
                if items:
                    new_ds["linkedAlerts"].append(
                        {
                            "id": items[0][0],
                            "attributes": {
                                "prsStore": items[0][2]["prsStore"][0]
                            }
                        }
                    )

            res["data"].append(new_ds)

        return res

    async def _further_update(self, mes: dict) -> None:

        ds_id = mes["data"]["id"]
        for item in mes["data"]["linkTags"]:
            copy_item = copy.deepcopy(item)
            copy_item["dataStorageId"] = ds_id
            await self._link_tag(copy_item)
        for item in mes["data"]["linkAlerts"]:
            copy_item = copy.deepcopy(item)
            copy_item["dataStorageId"] = ds_id
            await self._link_alert(copy_item)

    async def _unlink_tag(self, tag_id: str) -> None:
        """Метод отвязки тега от хранилища.
        Ищем, к какому хранилищу привязан тег и посылаем этому хранилищу
        сообщение об отвязке, после удаляем ссылку на тег.

        Args:
            tag_id (str): id отвязываемого тега
        """
        items = await self._hierarchy.search({
            "base": self._config.hierarchy["node_id"],
            "scope": hierarchy.CN_SCOPE_SUBTREE,
            "filter": {
                "cn": f"{tag_id}",
                "objectClass": f"prsDatastorageTagData"
            },
            "attributes": ["cn"]
        })
        if not items:
            self._logger.info(
                f"Тег {tag_id} не привязан ни к одному хранилищу."
            )
            return

        datastorage_id = await self._hierarchy.get_node_id(
            dn2str(str2dn(items[0][1])[2:])
        )

        routing_key = self._config["publish"]["main"]["routing_key"][0]

        await self._post_message(mes={"action": "unlinkTag", "id": [tag_id]},
            routing_key=routing_key)

        await self._hierarchy.delete(items[0][0])

        self._logger.info(
            f"Послано сообщение об отвязке тега {tag_id} "
            f"от хранилища {datastorage_id}"
        )

    async def _unlink_alert(self, alert_id: str) -> None:
        """Метод отвязки тревоги от хранилища.
        Ищем, к какому хранилищу привязана тревога и посылаем этому хранилищу
        сообщение об отвязке, после удаляем ссылку на тревогу.

        Args:
            alert_id (str): id отвязываемой тревоги
        """
        items = await self._hierarchy.search({
            "base": self._config.hierarchy["node_id"],
            "scope": hierarchy.CN_SCOPE_SUBTREE,
            "filter": {
                "cn": f"{alert_id}",
                "objectClass": "prsDatastorageAlertData"
            },
            "attributes": ["cn"]
        })
        if not items:
            self._logger.info(
                f"Тег {alert_id} не привязан ни к одному хранилищу."
            )
            return

        datastorage_id = await self._hierarchy.get_node_id(
            dn2str(str2dn(items[0][1])[2:])
        )

        routing_key = self._config["publish"]["main"]["routing_key"][0]

        await self._post_message(mes={"action": "unlinkTag", "id": [alert_id]},
            routing_key=routing_key)

        await self._hierarchy.delete(items[0][0])

        self._logger.info(
            f"Послано сообщение об отвязке тревоги {alert_id} "
            f"от хранилища {datastorage_id}"
        )

    async def _get_default_datastorage_id(self) -> str:
        items = await self._hierarchy.search({
                "base": self._config.hierarchy["node_id"],
                "filter": {
                    "objectClass": ["prsDataStorage"],
                    "prsDefault": ["TRUE"]
                },
                "scope": hierarchy.CN_SCOPE_ONELEVEL
            })

        if items:
            return items[0][0]
        return None

    async def _link_tag(self, payload: dict) -> None:
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
                "tagId": "tag_id",
                "dataStorageId": "ds_id",
                "attributes": {
                    "prsStore":
                }
            }
        """
        # если не передан datastorage_id, привязываем тег к хранилищу
        # по умолчанию
        if not payload.get("dataStorageId"):
            datastorage_id = await self._get_default_datastorage_id()
            if not datastorage_id:
                self._logger.info(
                    f"Невозможно привязать тег: "
                    f"нет хранилища данных по умолчанию."
                )
                return
            payload["dataStorageId"] = datastorage_id

        await self._unlink_tag(payload["tagId"])

        # res = {
        #   "prsStore": {...}
        # }
        # сообщение о привязке тега посылается с routing_key = <id хранилища>
        res = await self._post_message(
            mes={"action": "dataStorages.linkTag", "data": payload},
            reply=True,
            routing_key=payload["dataStorageId"])

        prs_store = res.get("prsStore")

        node_dn = await self._hierarchy.get_node_dn(payload['dataStorageId'])
        tags_node_id = await self._hierarchy.get_node_id(
            f"cn=tags,cn=system,{node_dn}"
        )
        new_node_id = await self._hierarchy.add(
            base=tags_node_id,
            attribute_values={
                "objectClass": ["prsDatastorageTagData"],
                "cn": payload["tagId"],
                "prsStore": prs_store
            }
        )
        await self._hierarchy.add_alias(
            parent_id=new_node_id,
            aliased_object_id=payload["tagId"],
            alias_name=payload["tagId"]
        )

        self._logger.info(
            f"Тег {payload['tagId']} привязан к хранилищу {payload['dataStorageId']}"
        )

    async def _link_alert(self, payload: dict) -> None:
        """Метод привязки тревоги к хранилищу.

        Логика работы метода: предполагаем, что тревога может быть привязана
        только
        к одному хранилищу (может, есть смысл в привязке тревог сразу к
        нескольким хранилищам, чтобы данные писались одновременно в разные
        хранилища; только тут возникает вопрос: при чтении данных, из
        какого хранилища эти данные брать).

        Если тревога уже привязана к какому-либо хранилищу (ищем ссылку на
        эту тревогу
        в иерархии ``cn=dataStorages,cn=prs``), то сначала отвязываем тревогу
        от предыдущего хранилища, затем привязываем к новому.

        Args:
            payload (dict): {
                "alertId": "alert_id",
                "attributes": {
                    "prsStore":
                }
            }
        """
        # если не передан datastorage_id, привязываем тревогу к хранилищу
        # по умолчанию
        if not payload.get("dataStorageId"):
            datastorage_id = await self._get_default_datastorage_id()
            if not datastorage_id:
                self._logger.info(
                    f"Невозможно привязать тревогу: "
                    f"нет хранилища данных по умолчанию."
                )
                return
            payload["dataStorageId"] = datastorage_id

        await self._unlink_alert(payload["alertId"])

        # res = {
        #   "prsStore": {...}
        # }
        # сообщение о привязке тега посылается с routing_key = <id хранилища>
        res = await self._post_message(
            mes={"action": "dataStorages.linkAlert", "data": payload},
            reply=True,
            routing_key=payload["dataStorageId"])

        prs_store = res.get("prsStore")

        node_dn = await self._hierarchy.get_node_dn(payload['dataStorageId'])
        alerts_node_id = await self._hierarchy.get_node_id(
            f"cn=alerts,cn=system,{node_dn}"
        )
        new_node_id = await self._hierarchy.add(
            base=alerts_node_id,
            attribute_values={
                "objectClass": ["prsDatastorageAlertData"],
                "cn": payload["alertId"],
                "prsStore": prs_store
            }
        )
        await self._hierarchy.add_alias(
            parent_id=new_node_id,
            aliased_object_id=payload["alertId"],
            alias_name=payload["alertId"]
        )

        self._logger.info(
            f"Тревога {payload['alertId']} привязана к хранилищу {payload['dataStorageId']}"
        )

    async def _further_create(self, mes: dict, new_id: str) -> None:
        sys_ids = await self._hierarchy.search({
            "base": new_id,
            "scope": hierarchy.CN_SCOPE_ONELEVEL,
            "filter": {
                "cn": ["system"]
            }
        })

        sys_id = sys_ids[0][0]

        await self._hierarchy.add(sys_id, {"cn": "tags"})
        await self._hierarchy.add(sys_id, {"cn": "alerts"})

        for item in mes["data"]["linkTags"]:
            copy_item = copy.deepcopy(item)
            copy_item["dataStorageId"] = new_id
            await self._link_tag(copy_item)
        for item in mes["data"]["linkAlerts"]:
            copy_item = copy.deepcopy(item)
            copy_item["dataStorageId"] = new_id
            await self._link_alert(copy_item)

settings = DataStoragesModelCRUDSettings()

app = DataStoragesModelCRUD(settings=settings, title="DataStoragesModelCRUD")
