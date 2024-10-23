import sys
import copy
import json

sys.path.append(".")

from src.common import model_crud_svc
from src.common import hierarchy
from src.services.dataStorages.model_crud.dataStorages_model_crud_settings import DataStoragesModelCRUDSettings

class DataStoragesModelCRUD(model_crud_svc.ModelCRUDSvc):
    """Сервис работы с хранилищами данных в иерархии.

    Подписывается на очередь ``dataStorages_api_crud`` обменника ``dataStorages_api_crud``\,
    в которую публикует сообщения сервис ``dataStorages_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """
    def __init__(self, settings: DataStoragesModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    async def _further_read(self, mes: dict, search_result: dict) -> dict:

        if not mes["getLinkedTags"] and not mes["getLinkedAlerts"]:
            return search_result

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
                        "attributes": ["cn", "prsStore"],
                        "scope": 2
                    }
                )
                if items:
                    for item in items:
                        new_ds["linkedTags"].append(
                            {
                                "tagId": item[2]["cn"][0],
                                "attributes": {
                                    "cn": item[2]["cn"][0],
                                    "prsStore": json.loads(item[2]["prsStore"][0]),
                                    "objectClass": "prsDatastorageTagData"
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
                        "attributes": ["cn", "prsStore"],
                        "scope": 2
                    }
                )
                if items:
                    for item in items:
                        new_ds["linkedAlerts"].append(
                            {
                                "alertId": item[2]["cn"][0],
                                "attributes": {
                                    "cn": item[2]["cn"][0],
                                    "prsStore": json.loads(item[2]["prsStore"][0]),
                                    "objectClass": "prsDatastorageAlertData"
                                }
                            }
                        )

            res["data"].append(new_ds)

        return res

    async def _further_update(self, mes: dict) -> None:

        ds_id = mes["id"]
        
        linked_tags = mes.get('linkTags')
        if linked_tags:
            for item in linked_tags:
                copy_item = copy.deepcopy(item)
                copy_item["dataStorageId"] = ds_id
                await self._link_tag(copy_item)
        
        linked_alerts = mes.get('linkAlerts')
        if linked_alerts:
            for item in linked_alerts:
                copy_item = copy.deepcopy(item)
                copy_item["dataStorageId"] = ds_id
                await self._link_alert(copy_item)

        unlinked_tags = mes.get("unlinkTags")
        if unlinked_tags:
            for tag_id in unlinked_tags:
                item = {
                    "tagId": tag_id,
                    "dataStorageId": ds_id
                }
                await self._unlink_tag(item)

        unlinked_alerts = mes.get("unlinkAlerts")
        if unlinked_alerts:
            for alert_id in unlinked_alerts:
                item = {
                    "alertId": alert_id,
                    "dataStorageId": ds_id
                }
                await self._unlink_alert(item)
        
    async def _unlink_tag(self, item: dict, routing_key: str = None) -> None:
        """Метод отвязки тега от хранилища.
        Ищем, к какому хранилищу привязан тег и посылаем этому хранилищу
        сообщение об отвязке, после удаляем ссылку на тег.

        Args:
            tag_id (str): id отвязываемого тега
        """
        
        res = await self._post_message(
            mes=item, routing_key=f"{self._config.hierarchy['class']}.model.unlink_tag.{item['dataStorageId']}"
        )
        if res is None:
            self._logger.error(f"{self._config.svc_name} :: Нет обработчика для хранилища '{item['dataStorageId']}'.")
            return

        res = await self._hierarchy.search(payload={
            "base": item['dataStorageId'],
            "filter": {
                "objectClass": ["prsDatastorageTagData"]
            },
            "attributes": ["cn"]
        })
        if not res:
            self._logger.error(f"{self._config.svc_name} :: Нет данных о привязке тега '{item['tagId']}' к хранилищу '{item['dataStorageId']}'.")
            return

        await self._hierarchy.delete(res[0][0])

        self._logger.info(
            f"{self._config.svc_name} :: Тег {item['tagId']} отвязан от хранилища {item['dataStorageId']}."
        )

    async def _unlink_alert(self, item: dict, routing_key: str = None) -> None:
        """Метод отвязки тревоги от хранилища.
        Ищем, к какому хранилищу привязана тревога и посылаем этому хранилищу
        сообщение об отвязке, после удаляем ссылку на тревогу.

        Args:
            alert_id (str): id отвязываемой тревоги
        """
        res = await self._post_message(
            mes=item, routing_key=f"{self._config.hierarchy['class']}.model.unlink_alert.{item['dataStorageId']}"
        )
        if res is None:
            self._logger.error(f"{self._config.svc_name} :: Нет обработчика для хранилища '{item['dataStorageId']}'.")
            return

        res = await self._hierarchy.search(payload={
            "base": item['dataStorageId'],
            "filter": {
                "objectClass": ["prsDatastorageAlertData"]
            },
            "attributes": ["cn"]
        })
        if not res:
            self._logger.error(f"{self._config.svc_name} :: Нет данных о привязке тревоги '{item['alertId']}' к хранилищу '{item['dataStorageId']}'.")
            return

        await self._hierarchy.delete(res[0][0])

        self._logger.info(
            f"{self._config.svc_name} :: Тревога {item['alertId']} отвязана от хранилища {item['dataStorageId']}."
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

    async def _link_tag(self, payload: dict, routing_key: str = None) -> None:
        """Метод привязки тега к хранилищу.

        Метод создаёт новый узел в списке тегов хранилища.

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
                self._logger.error(
                    f"{self._config.svc_name} :: Невозможно привязать тег: "
                    f"нет хранилища данных по умолчанию."
                )
                return
            payload["dataStorageId"] = datastorage_id

        datastorage_id = payload["dataStorageId"]

        # res = {
        #   "prsStore": {...}
        # }
        res = await self._post_message(
            mes=payload,
            reply=True,
            routing_key=f"{self._config.hierarchy['class']}.model.link_tag.{datastorage_id}")
        if not res:
            self._logger.error(f"{self._config.svc_name} :: Нет обработчика для хранилища {datastorage_id}.")
            return
        
        get_tag = {
            "id": payload['tagId'],
            "attributes": ["prsValueTypeCode"]
        }
        tag_data = await self._hierarchy.search(payload=get_tag)
        if not tag_data:
            self._logger.error(f"{self._config.svc_name} :: Нет данных по тегу {payload['id']}.")
            return

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
                "prsStore": prs_store,
                "prsJsonConfigString": {
                    "prsValueTypeCode": int(tag_data[0][2]["prsValueTypeCode"][0])
                }
            }
        )
        await self._hierarchy.add_alias(
            parent_id=new_node_id,
            aliased_object_id=payload["tagId"],
            alias_name=payload["tagId"]
        )        

        self._logger.info(
            f"{self._config.svc_name} :: Тег {payload['tagId']} привязан к хранилищу {payload['dataStorageId']}"
        )

    async def _link_alert(self, payload: dict, routing_key: str = None) -> None:
        """Метод привязки тревоги к хранилищу.

        Логика работы метода: предполагаем, что тревога может быть привязана
        только
        к одному хранилищу (может, есть смысл в привязке тревог сразу к
        нескольким хранилищам, чтобы данные писались одновременно в разные
        хранилища; только тут возникает вопрос: при чтении данных, из
        какого хранилища эти данные брать).

        Если тревога уже привязана к какому-либо хранилищу (ищем ссылку на
        эту тревогу
        в иерархии ``cn=dataStorages,cn=prs``\), то сначала отвязываем тревогу
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
                    f"{self._config.svc_name} :: Невозможно привязать тревогу: "
                    f"нет хранилища данных по умолчанию."
                )
                return
            payload["dataStorageId"] = datastorage_id

        datastorage_id = payload["dataStorageId"]

        #await self._unlink_alert(payload["alertId"])

        # res = {
        #   "prsStore": {...}
        # }
        # сообщение о привязке тега посылается с routing_key = <id хранилища>
        res = await self._post_message(
            mes=payload,
            reply=True,
            routing_key=f"{self._config.hierarchy['class']}.model.link_alert.{datastorage_id}")
        
        if not res:
            self._logger.error(f"{self._config.svc_name} :: Нет обработчика для хранилища {datastorage_id}.")
            return

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
            f"{self._config.svc_name} :: Тревога {payload['alertId']} привязана к хранилищу {payload['dataStorageId']}"
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

        for item in mes["linkTags"]:
            copy_item = copy.deepcopy(item)
            copy_item["dataStorageId"] = new_id
            await self._link_tag(copy_item)
        for item in mes["linkAlerts"]:
            copy_item = copy.deepcopy(item)
            copy_item["dataStorageId"] = new_id
            await self._link_alert(copy_item)

settings = DataStoragesModelCRUDSettings()

app = DataStoragesModelCRUD(settings=settings, title="DataStoragesModelCRUD")
