import sys
import copy
import json
from typing import Any

sys.path.append(".")

from src.common import hierarchy
from src.services.dataStorages.model_crud.dataStorages_model_crud_svc import DataStoragesModelCRUD
from src.services.dataStorages.model_crud.dataStorages_model_crud_v2_settings import (
    DataStoragesModelCRUDV2Settings,
)


class DataStoragesModelCRUDV2(DataStoragesModelCRUD):
    """v2 model_crud расширяет v1:
    - операции cn=system/operations (create/update/read/delete)
    - расширенная привязка тегов (prsEntityTypeCode/prsJsonConfigString) для интеграционных тегов
    """

    async def _further_read(self, mes: dict, search_result: dict) -> dict:
        res = await super()._further_read(mes, search_result)
        if not mes.get("getLinkedOperations"):
            return res

        for ds in res["data"]:
            ds_id = ds["id"]
            ds["operations"] = await self._read_ds_operations(ds_id=ds_id)
        return res

    async def _further_create(self, mes: dict, new_id: str) -> None:
        await self._ensure_ds_system_nodes(ds_id=new_id)

        ops = mes.get("operations") or []
        if ops:
            await self._sync_operations(ds_id=new_id, operations=ops, replace=True)

    async def _further_update(self, mes: dict) -> None:
        ds_id = mes["id"]

        if "operations" in mes and mes.get("operations") is not None:
            await self._sync_operations(ds_id=ds_id, operations=mes["operations"])
        else:
            unlink_ops = mes.get("unlinkOperations") or []
            if unlink_ops:
                await self._delete_operations_by_cn(ds_id=ds_id, operation_cns=unlink_ops)

        await super()._further_update(mes)

    async def _ensure_ds_system_nodes(self, ds_id: str) -> None:
        ds_dn = await self._hierarchy.get_node_dn(ds_id)
        if not ds_dn:
            raise ValueError(f"Не удалось получить DN хранилища {ds_id}.")

        system_id = await self._hierarchy.get_node_id(f"cn=system,{ds_dn}")
        if not system_id:
            system_id = await self._hierarchy.add(ds_id, {"cn": ["system"]})

        for cn in ("tags", "alerts", "operations"):
            child_id = await self._hierarchy.get_node_id(f"cn={cn},cn=system,{ds_dn}")
            if not child_id:
                await self._hierarchy.add(
                    base=system_id,
                    attribute_values={"cn": [cn], "prsSystemNode": True},
                )

    async def _read_ds_operations(self, ds_id: str) -> list[dict]:
        ds_dn = await self._hierarchy.get_node_dn(ds_id)
        if not ds_dn:
            return []
        ops_node_id = await self._hierarchy.get_node_id(f"cn=operations,cn=system,{ds_dn}")
        if not ops_node_id:
            return []

        ops = await self._hierarchy.search(
            {
                "base": ops_node_id,
                "scope": hierarchy.CN_SCOPE_ONELEVEL,
                "filter": {"objectClass": ["prsDatastorageOperation"]},
                "attributes": ["cn", "prsActive", "prsEntityTypeCode", "prsJsonConfigString"],
                "deref": False,
            }
        )
        if not ops:
            return []

        result: list[dict] = []
        for op_id, _, attrs in ops:
            op_cfg_attr = attrs.get("prsJsonConfigString")
            op_cfg = json.loads(op_cfg_attr[0]) if op_cfg_attr else {}

            params = await self._hierarchy.search(
                {
                    "base": op_id,
                    "scope": hierarchy.CN_SCOPE_ONELEVEL,
                    "filter": {"objectClass": ["prsDatastorageOperationParameter"]},
                    "attributes": ["cn", "prsActive", "prsJsonConfigString"],
                    "deref": False,
                }
            )
            param_items: list[dict] = []
            for _, __, p_attrs in params or []:
                p_cfg_attr = p_attrs.get("prsJsonConfigString")
                p_cfg = json.loads(p_cfg_attr[0]) if p_cfg_attr else {}
                param_items.append(
                    {
                        "cn": p_attrs["cn"][0],
                        "prsActive": p_attrs.get("prsActive", ["TRUE"])[0] == "TRUE",
                        "prsJsonConfigString": p_cfg,
                    }
                )

            result.append(
                {
                    "cn": attrs["cn"][0],
                    "prsActive": attrs.get("prsActive", ["TRUE"])[0] == "TRUE",
                    "prsEntityTypeCode": int(attrs.get("prsEntityTypeCode", ["0"])[0]),
                    "prsJsonConfigString": op_cfg,
                    "parameters": param_items,
                }
            )

        return result

    async def _delete_operations_by_cn(self, ds_id: str, operation_cns: list[str]) -> None:
        await self._ensure_ds_system_nodes(ds_id=ds_id)
        ds_dn = await self._hierarchy.get_node_dn(ds_id)
        if not ds_dn:
            return
        ops_node_id = await self._hierarchy.get_node_id(f"cn=operations,cn=system,{ds_dn}")
        if not ops_node_id:
            return

        for op_cn in operation_cns:
            if not op_cn:
                continue
            found = await self._hierarchy.search(
                {
                    "base": ops_node_id,
                    "scope": hierarchy.CN_SCOPE_ONELEVEL,
                    "filter": {"objectClass": ["prsDatastorageOperation"], "cn": [op_cn]},
                    "attributes": ["cn"],
                    "deref": False,
                }
            )
            if found:
                await self._hierarchy.delete(found[0][0])

    async def _sync_operations(self, ds_id: str, operations: list[dict[str, Any]], replace: bool = True) -> None:
        await self._ensure_ds_system_nodes(ds_id=ds_id)

        ds_dn = await self._hierarchy.get_node_dn(ds_id)
        operations_node_id = await self._hierarchy.get_node_id(f"cn=operations,cn=system,{ds_dn}")
        if not operations_node_id:
            self._logger.error(f"{self._config.svc_name} :: Нет узла operations у хранилища {ds_id}.")
            return

        existing_ops = await self._hierarchy.search(
            {
                "base": operations_node_id,
                "scope": hierarchy.CN_SCOPE_ONELEVEL,
                "filter": {"objectClass": ["prsDatastorageOperation"]},
                "attributes": ["cn", "prsActive", "prsEntityTypeCode", "prsJsonConfigString"],
                "deref": False,
            }
        )
        existing_by_cn = {item[2]["cn"][0]: item for item in (existing_ops or [])}

        desired_cns = set()
        for op in operations:
            op_cn = op.get("cn")
            if not op_cn:
                continue
            desired_cns.add(op_cn)

            op_active = op.get("prsActive", True)
            op_kind = op.get("prsEntityTypeCode", 0)
            op_cfg = op.get("prsJsonConfigString") or {}

            existed = existing_by_cn.get(op_cn)
            if not existed:
                op_id = await self._hierarchy.add(
                    base=operations_node_id,
                    attribute_values={
                        "objectClass": ["prsDatastorageOperation"],
                        "cn": op_cn,
                        "prsActive": op_active,
                        "prsEntityTypeCode": op_kind,
                        "prsJsonConfigString": op_cfg,
                    },
                )
            else:
                op_id = existed[0]
                await self._hierarchy.modify(
                    op_id,
                    {
                        "prsActive": op_active,
                        "prsEntityTypeCode": op_kind,
                        "prsJsonConfigString": op_cfg,
                    },
                )

            await self._sync_operation_parameters(op_id=op_id, parameters=op.get("parameters") or [], replace=True)

        if replace:
            for op_cn, existed in existing_by_cn.items():
                if op_cn not in desired_cns:
                    await self._hierarchy.delete(existed[0])

    async def _sync_operation_parameters(self, op_id: str, parameters: list[dict[str, Any]], replace: bool = True) -> None:
        existing = await self._hierarchy.search(
            {
                "base": op_id,
                "scope": hierarchy.CN_SCOPE_ONELEVEL,
                "filter": {"objectClass": ["prsDatastorageOperationParameter"]},
                "attributes": ["cn", "prsActive", "prsJsonConfigString"],
                "deref": False,
            }
        )
        existing_by_cn = {item[2]["cn"][0]: item for item in (existing or [])}

        desired_cns = set()
        for p in parameters:
            p_cn = p.get("cn")
            if not p_cn:
                continue
            desired_cns.add(p_cn)

            p_active = p.get("prsActive", True)
            p_cfg = p.get("prsJsonConfigString") or {}

            existed = existing_by_cn.get(p_cn)
            if not existed:
                await self._hierarchy.add(
                    base=op_id,
                    attribute_values={
                        "objectClass": ["prsDatastorageOperationParameter"],
                        "cn": p_cn,
                        "prsActive": p_active,
                        "prsJsonConfigString": p_cfg,
                    },
                )
            else:
                await self._hierarchy.modify(
                    existed[0],
                    {"prsActive": p_active, "prsJsonConfigString": p_cfg},
                )

        if replace:
            for p_cn, existed in existing_by_cn.items():
                if p_cn not in desired_cns:
                    await self._hierarchy.delete(existed[0])

    async def _link_tag(self, payload: dict, routing_key: str | None = None) -> None:
        """v2: сохраняем расширенную конфигурацию привязки."""
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

        get_tag = {"id": payload["tagId"], "attributes": ["prsValueTypeCode"]}
        tag_data = await self._hierarchy.search(payload=get_tag)
        if not tag_data:
            self._logger.error(f"{self._config.svc_name} :: Нет данных по тегу {payload['id']}.")
            return

        prs_store = res.get("prsStore")

        node_dn = await self._hierarchy.get_node_dn(payload["dataStorageId"])
        tags_node_id = await self._hierarchy.get_node_id(f"cn=tags,cn=system,{node_dn}")

        link_attrs = payload.get("attributes") or {}
        link_entity_type = link_attrs.get("prsEntityTypeCode")
        link_cfg = link_attrs.get("prsJsonConfigString") or {}
        link_cfg = copy.deepcopy(link_cfg)
        link_cfg["prsValueTypeCode"] = int(tag_data[0][2]["prsValueTypeCode"][0])

        attr_vals = {
            "objectClass": ["prsDatastorageTagData"],
            "cn": payload["tagId"],
            "prsJsonConfigString": link_cfg,
        }
        if prs_store is not None:
            attr_vals["prsStore"] = prs_store
        if link_entity_type is not None:
            attr_vals["prsEntityTypeCode"] = int(link_entity_type)

        new_node_id = await self._hierarchy.add(base=tags_node_id, attribute_values=attr_vals)
        await self._hierarchy.add_alias(
            parent_id=new_node_id,
            aliased_object_id=payload["tagId"],
            alias_name=payload["tagId"],
        )

        self._logger.info(
            f"{self._config.svc_name} :: Тег {payload['tagId']} привязан к хранилищу {payload['dataStorageId']}"
        )


settings = DataStoragesModelCRUDV2Settings()
app = DataStoragesModelCRUDV2(settings=settings, title="DataStoragesModelCRUDV2")

