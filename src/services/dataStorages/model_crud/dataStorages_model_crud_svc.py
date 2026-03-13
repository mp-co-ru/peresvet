import sys
import copy
import json
from src.common import model_crud_svc
from src.common import hierarchy
from src.common.model_crud_settings import ModelCRUDSettings
from src.services.dataStorages.model_crud.dataStorages_model_crud_settings import DataStoragesModelCRUDSettings


class DataStoragesModelCRUD(model_crud_svc.ModelCRUDSvc):
    """v1 model_crud для dataStorages (без v2 operations)."""

    def __init__(self, settings: ModelCRUDSettings, *args, **kwargs):
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
                        "filter": {"objectClass": ["prsDatastorageTagData"]},
                        "attributes": ["cn", "prsStore"],
                        "scope": 2,
                    }
                )
                if items:
                    for item in items:
                        prs_store_attr = item[2].get("prsStore")
                        prs_store_val = self._safe_json_attr(prs_store_attr, default=None)
                        new_ds["linkedTags"].append(
                            {
                                "tagId": item[2]["cn"][0],
                                "attributes": {
                                    "cn": item[2]["cn"][0],
                                    "prsStore": prs_store_val,
                                    "objectClass": "prsDatastorageTagData",
                                },
                            }
                        )

            if mes["getLinkedAlerts"]:
                new_ds["linkedAlerts"] = []
                items = await self._hierarchy.search(
                    {
                        "base": ds_id,
                        "filter": {"objectClass": ["prsDatastorageAlertData"]},
                        "attributes": ["cn", "prsStore"],
                        "scope": 2,
                    }
                )
                if items:
                    for item in items:
                        prs_store_attr = item[2].get("prsStore")
                        prs_store_val = self._safe_json_attr(prs_store_attr, default=None)
                        new_ds["linkedAlerts"].append(
                            {
                                "alertId": item[2]["cn"][0],
                                "attributes": {
                                    "cn": item[2]["cn"][0],
                                    "prsStore": prs_store_val,
                                    "objectClass": "prsDatastorageAlertData",
                                },
                            }
                        )

            res["data"].append(new_ds)

        return res

    def _safe_json_attr(self, ldap_attr, default=None):
        if not ldap_attr:
            return default
        raw = ldap_attr[0] if isinstance(ldap_attr, list) else ldap_attr
        if raw is None:
            return default
        if isinstance(raw, (dict, list, int, float, bool)):
            return raw
        if isinstance(raw, str):
            s = raw.strip()
            if s == "":
                return default
            try:
                return json.loads(s)
            except Exception:
                return raw
        return raw

    async def _further_create(self, mes: dict, new_id: str) -> None:
        """v1: ensure system child nodes `tags` and `alerts` exist.

        Note: base `ModelCRUDSvc._create` always creates `cn=system` under the entity.
        """
        ds_dn = await self._hierarchy.get_node_dn(new_id)
        if not ds_dn:
            self._logger.error(f"{self._config.svc_name} :: Не удалось получить DN хранилища {new_id}.")
            return

        system_dn = f"cn=system,{ds_dn}"
        system_id = await self._hierarchy.get_node_id(system_dn)
        if not system_id:
            # safety net: should already exist, but keep behavior robust
            system_id = await self._hierarchy.add(new_id, {"cn": ["system"]})

        for cn in ("tags", "alerts"):
            child_dn = f"cn={cn},cn=system,{ds_dn}"
            child_id = await self._hierarchy.get_node_id(child_dn)
            if child_id:
                continue
            await self._hierarchy.add(
                base=system_id,
                attribute_values={"cn": [cn], "prsSystemNode": True},
            )

    async def _further_update(self, mes: dict) -> None:
        ds_id = mes["id"]

        linked_tags = mes.get("linkedTags")
        if linked_tags:
            for item in linked_tags:
                copy_item = copy.deepcopy(item)
                copy_item["dataStorageId"] = ds_id
                await self._link_tag(copy_item)

        linked_alerts = mes.get("linkedAlerts")
        if linked_alerts:
            for item in linked_alerts:
                copy_item = copy.deepcopy(item)
                copy_item["dataStorageId"] = ds_id
                await self._link_alert(copy_item)

        unlinked_tags = mes.get("unlinkTags")
        if unlinked_tags:
            for tag_id in unlinked_tags:
                await self._unlink_tag({"tagId": tag_id, "dataStorageId": ds_id})

        unlinked_alerts = mes.get("unlinkAlerts")
        if unlinked_alerts:
            for alert_id in unlinked_alerts:
                await self._unlink_alert({"alertId": alert_id, "dataStorageId": ds_id})

    async def _unlink_tag(self, item: dict, routing_key: str | None = None) -> None:
        res = await self._post_message(
            mes=item, routing_key=f"{self._config.hierarchy['class']}.model.unlink_tag.{item['dataStorageId']}"
        )
        if res is None:
            self._logger.error(f"{self._config.svc_name} :: Нет обработчика для хранилища '{item['dataStorageId']}'.")
            return

        res = await self._hierarchy.search(
            payload={
                "base": item["dataStorageId"],
                "filter": {"objectClass": ["prsDatastorageTagData"], "cn": [item["tagId"]]},
                "attributes": ["cn"],
            }
        )
        if not res:
            self._logger.error(
                f"{self._config.svc_name} :: Нет данных о привязке тега '{item['tagId']}' к хранилищу '{item['dataStorageId']}'."
            )
            return

        await self._hierarchy.delete(res[0][0])

        self._logger.info(
            f"{self._config.svc_name} :: Тег {item['tagId']} отвязан от хранилища {item['dataStorageId']}."
        )

    async def _unlink_alert(self, item: dict, routing_key: str | None = None) -> None:
        res = await self._post_message(
            mes=item, routing_key=f"{self._config.hierarchy['class']}.model.unlink_alert.{item['dataStorageId']}"
        )
        if res is None:
            self._logger.error(f"{self._config.svc_name} :: Нет обработчика для хранилища '{item['dataStorageId']}'.")
            return

        res = await self._hierarchy.search(
            payload={
                "base": item["dataStorageId"],
                "filter": {"objectClass": ["prsDatastorageAlertData"], "cn": [item["alertId"]]},
                "attributes": ["cn"],
            }
        )
        if not res:
            self._logger.error(
                f"{self._config.svc_name} :: Нет данных о привязке тревоги '{item['alertId']}' к хранилищу '{item['dataStorageId']}'."
            )
            return

        await self._hierarchy.delete(res[0][0])

        self._logger.info(
            f"{self._config.svc_name} :: Тревога {item['alertId']} отвязана от хранилища {item['dataStorageId']}."
        )

    async def _get_default_datastorage_id(self) -> str | None:
        items = await self._hierarchy.search(
            {
                "base": self._config.hierarchy["node_id"],
                "filter": {"objectClass": ["prsDataStorage"], "prsDefault": ["TRUE"]},
                "scope": hierarchy.CN_SCOPE_ONELEVEL,
            }
        )

        if items:
            return items[0][0]
        return None

    async def _link_tag(self, payload: dict, routing_key: str | None = None) -> None:
        if not payload.get("dataStorageId"):
            datastorage_id = await self._get_default_datastorage_id()
            if not datastorage_id:
                self._logger.error(
                    f"{self._config.svc_name} :: Невозможно привязать тег: нет хранилища данных по умолчанию."
                )
                return
            payload["dataStorageId"] = datastorage_id

        datastorage_id = payload["dataStorageId"]

        res = await self._post_message(
            mes=payload,
            reply=True,
            routing_key=f"{self._config.hierarchy['class']}.model.link_tag.{datastorage_id}",
        )
        if not res:
            self._logger.error(f"{self._config.svc_name} :: Нет обработчика для хранилища {datastorage_id}.")
            return
        if not isinstance(res, dict):
            self._logger.error(f"{self._config.svc_name} :: Некорректный ответ обработчика хранилища {datastorage_id}.")
            return

        get_tag = {"id": payload["tagId"], "attributes": ["prsValueTypeCode"]}
        tag_data = await self._hierarchy.search(payload=get_tag)
        if not tag_data:
            self._logger.error(f"{self._config.svc_name} :: Нет данных по тегу {payload['id']}.")
            return

        prs_store = res.get("prsStore")
        tag_value_type = int(tag_data[0][2]["prsValueTypeCode"][0])
        link_cfg = {} if tag_value_type == 5 else {"prsValueTypeCode": tag_value_type}

        node_dn = await self._hierarchy.get_node_dn(payload["dataStorageId"])
        tags_node_id = await self._hierarchy.get_node_id(f"cn=tags,cn=system,{node_dn}")
        add_vals: dict = {
            "objectClass": ["prsDatastorageTagData"],
            "cn": payload["tagId"],
            "prsStore": prs_store,
        }
        if link_cfg:
            add_vals["prsJsonConfigString"] = link_cfg
        new_node_id = await self._hierarchy.add(
            base=tags_node_id,
            attribute_values=add_vals,
        )
        await self._hierarchy.add_alias(
            parent_id=new_node_id,
            aliased_object_id=payload["tagId"],
            alias_name=payload["tagId"],
        )

        self._logger.info(
            f"{self._config.svc_name} :: Тег {payload['tagId']} привязан к хранилищу {payload['dataStorageId']}"
        )

    async def _link_alert(self, payload: dict, routing_key: str | None = None) -> None:
        if not payload.get("dataStorageId"):
            datastorage_id = await self._get_default_datastorage_id()
            if not datastorage_id:
                self._logger.info(
                    f"{self._config.svc_name} :: Невозможно привязать тревогу: нет хранилища данных по умолчанию."
                )
                return
            payload["dataStorageId"] = datastorage_id

        datastorage_id = payload["dataStorageId"]

        res = await self._post_message(
            mes=payload,
            reply=True,
            routing_key=f"{self._config.hierarchy['class']}.model.link_alert.{datastorage_id}",
        )
        if not res:
            self._logger.error(f"{self._config.svc_name} :: Нет обработчика для хранилища {datastorage_id}.")
            return
        if not isinstance(res, dict):
            self._logger.error(f"{self._config.svc_name} :: Некорректный ответ обработчика хранилища {datastorage_id}.")
            return

        prs_store = res.get("prsStore")

        node_dn = await self._hierarchy.get_node_dn(payload["dataStorageId"])
        alerts_node_id = await self._hierarchy.get_node_id(f"cn=alerts,cn=system,{node_dn}")
        new_node_id = await self._hierarchy.add(
            base=alerts_node_id,
            attribute_values={
                "objectClass": ["prsDatastorageAlertData"],
                "cn": payload["alertId"],
                "prsStore": prs_store,
            },
        )
        await self._hierarchy.add_alias(
            parent_id=new_node_id,
            aliased_object_id=payload["alertId"],
            alias_name=payload["alertId"],
        )

        self._logger.info(
            f"{self._config.svc_name} :: Тревога {payload['alertId']} привязана к хранилищу {payload['dataStorageId']}"
        )


settings = DataStoragesModelCRUDSettings()
app = DataStoragesModelCRUD(settings=settings, title="DataStoragesModelCRUD")
