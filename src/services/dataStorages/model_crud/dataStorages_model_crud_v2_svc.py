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
    - расширенная привязка тегов (prsJsonConfigString и опциональный prsEntityTypeCode) для интеграционных тегов
    - операции привязки интеграционного тега как дочерние LDAP-узлы linkedTags[].operations
    """

    _empty_optional_add_attrs = {"description"}

    async def _further_read(self, mes: dict, search_result: dict) -> dict:
        res = await super()._further_read(mes, search_result)

        if mes.get("getLinkedTags"):
            for ds in res["data"]:
                ds_id = ds["id"]
                for link in ds.get("linkedTags") or []:
                    tag_id = link.get("tagId")
                    if not tag_id:
                        continue
                    link["operations"] = await self._read_tag_link_operations(ds_id=ds_id, tag_id=tag_id)
        return res

    async def _further_create(self, mes: dict, new_id: str) -> None:
        # v2 keeps v1 create behavior; link operations are handled inside linkedTags update path.
        await super()._further_create(mes, new_id)

    async def _further_update(self, mes: dict) -> None:
        # v2 link operations are stored under linkedTags nodes; no cn=operations subtree maintenance.
        await super()._further_update(mes)

    async def _ensure_ds_operations_node(self, ds_id: str) -> None:
        ds_dn = await self._hierarchy.get_node_dn(ds_id)
        if not ds_dn:
            raise ValueError(f"Не удалось получить DN хранилища {ds_id}.")

        system_id = await self._hierarchy.get_node_id(f"cn=system,{ds_dn}")
        if not system_id:
            system_id = await self._hierarchy.add(ds_id, {"cn": ["system"]})

        ops_dn = f"cn=operations,cn=system,{ds_dn}"
        ops_id = await self._hierarchy.get_node_id(ops_dn)
        if not ops_id:
            await self._hierarchy.add(
                base=system_id,
                attribute_values={"cn": ["operations"], "prsSystemNode": True},
            )

    async def _delete_ds_operations_node(self, ds_id: str) -> None:
        ds_dn = await self._hierarchy.get_node_dn(ds_id)
        if not ds_dn:
            return
        ops_id = await self._hierarchy.get_node_id(f"cn=operations,cn=system,{ds_dn}")
        if ops_id:
            await self._hierarchy.delete(ops_id)

    async def _get_ds_type_after_update(self, ds_id: str, mes: dict) -> int | None:
        """Return current `prsEntityTypeCode` after LDAP modify has been applied."""
        attrs = mes.get("attributes") or {}
        v = attrs.get("prsEntityTypeCode") if isinstance(attrs, dict) else None
        if isinstance(v, list):
            v = v[0] if v else None
        if v is not None:
            try:
                return int(v)
            except Exception:
                return None

        # Fallback: read from LDAP
        node = await self._hierarchy.search(
            {
                "id": [ds_id],
                "attributes": ["prsEntityTypeCode"],
                "deref": False,
            }
        )
        if not node:
            return None
        raw = node[0][2].get("prsEntityTypeCode")
        if not raw:
            return None
        try:
            return int(raw[0])
        except Exception:
            return None

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
                p_cfg = self._safe_json_attr(p_cfg_attr, default={})
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

    async def _find_tag_link_node_id(self, ds_id: str, tag_id: str) -> str | None:
        found = await self._hierarchy.search(
            payload={
                "base": ds_id,
                "scope": hierarchy.CN_SCOPE_SUBTREE,
                "filter": {"objectClass": ["prsDatastorageTagData"], "cn": [tag_id]},
                "attributes": ["cn"],
                "deref": False,
            }
        )
        if not found:
            return None
        return found[0][0]

    async def _read_tag_link_operations(self, ds_id: str, tag_id: str) -> list[dict]:
        link_id = await self._find_tag_link_node_id(ds_id=ds_id, tag_id=tag_id)
        if not link_id:
            return []

        ops = await self._hierarchy.search(
            {
                "base": link_id,
                "scope": hierarchy.CN_SCOPE_ONELEVEL,
                "filter": {"objectClass": ["prsDatastorageTagOperation"]},
                "attributes": ["*"],
                "deref": False,
            }
        )
        if not ops:
            return []

        result: list[dict] = []
        for op_id, _, attrs in ops:
            op_cfg_attr = attrs.get("prsJsonConfigString")
            op_cfg = self._safe_json_attr(op_cfg_attr, default={})

            params = await self._hierarchy.search(
                {
                    "base": op_id,
                    "scope": hierarchy.CN_SCOPE_ONELEVEL,
                    "filter": {"objectClass": ["prsDatastorageTagOperationParameter"]},
                    "attributes": ["*"],
                    "deref": False,
                }
            )
            param_items: list[dict] = []
            for _, __, p_attrs in params or []:
                param_items.append(
                    {
                        "attributes": self._ldap_attrs_to_payload(p_attrs)
                    }
                )

            result.append(
                {
                    "attributes": self._ldap_attrs_to_payload(attrs),
                    "parameters": param_items,
                }
            )

        return result

    async def _delete_operations_by_cn(self, ds_id: str, operation_cns: list[str]) -> None:
        await self._ensure_ds_operations_node(ds_id=ds_id)
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
        await self._ensure_ds_operations_node(ds_id=ds_id)

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

    def _attrs_dict(self, item: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(item, dict):
            return {}
        attrs = item.get("attributes")
        if isinstance(attrs, dict):
            return attrs
        return item

    def _prepare_node_attrs(
        self,
        attrs: dict[str, Any],
        *,
        object_class: str,
        defaults: dict[str, Any] | None = None,
        drop_keys: set[str] | None = None,
    ) -> dict[str, Any]:
        vals = copy.deepcopy(attrs or {})
        for k in (drop_keys or set()):
            vals.pop(k, None)
        for k, v in (defaults or {}).items():
            if vals.get(k) is None:
                vals[k] = copy.deepcopy(v)
        vals["objectClass"] = [object_class]
        return vals

    def _prepare_node_add_attrs(self, attrs: dict[str, Any]) -> dict[str, Any]:
        vals = copy.deepcopy(attrs or {})
        for key in self._empty_optional_add_attrs:
            value = vals.get(key)
            if value is None or (isinstance(value, str) and not value):
                vals.pop(key, None)
            elif isinstance(value, list) and all(
                item is None or (isinstance(item, str) and not item) for item in value
            ):
                vals.pop(key, None)
        return vals

    def _ldap_attrs_to_payload(self, attrs: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, raw in attrs.items():
            if key in ("entryUUID", "prsIndex"):
                continue
            value: Any = raw
            if isinstance(raw, list):
                if len(raw) == 0:
                    value = None
                elif len(raw) == 1:
                    value = raw[0]
                else:
                    value = raw
            if key == "prsActive":
                if isinstance(value, str):
                    value = value.upper() == "TRUE"
                elif value is None:
                    value = True
            elif key == "prsEntityTypeCode":
                if value is None:
                    value = 0
                else:
                    value = int(value)
            elif key == "prsJsonConfigString":
                value = self._safe_json_attr(raw, default={})
            result[key] = value
        return result

    async def _sync_link_operations(self, link_id: str, operations: list[dict[str, Any]], replace: bool = True) -> None:
        existing_ops = await self._hierarchy.search(
            {
                "base": link_id,
                "scope": hierarchy.CN_SCOPE_ONELEVEL,
                "filter": {"objectClass": ["prsDatastorageTagOperation"]},
                "attributes": ["cn", "prsActive", "prsEntityTypeCode", "prsJsonConfigString"],
                "deref": False,
            }
        )
        existing_by_cn = {item[2]["cn"][0]: item for item in (existing_ops or [])}

        desired_cns = set()
        for op in operations or []:
            op_attrs = self._attrs_dict(op)
            op_cn = op_attrs.get("cn")
            if not op_cn:
                continue
            desired_cns.add(op_cn)

            operation_params = op.get("parameters") if isinstance(op, dict) else None
            if not isinstance(operation_params, list):
                nested_params = op_attrs.get("parameters")
                operation_params = nested_params if isinstance(nested_params, list) else []

            node_attrs = self._prepare_node_attrs(
                op_attrs,
                object_class="prsDatastorageTagOperation",
                defaults={
                    "prsActive": True,
                    "prsEntityTypeCode": 0,
                    "prsJsonConfigString": {},
                },
                drop_keys={"parameters"},
            )
            node_attrs["cn"] = op_cn

            existed = existing_by_cn.get(op_cn)
            if not existed:
                op_id = await self._hierarchy.add(
                    base=link_id,
                    attribute_values=self._prepare_node_add_attrs(node_attrs),
                )
            else:
                op_id = existed[0]
                modify_attrs = dict(node_attrs)
                modify_attrs.pop("objectClass", None)
                modify_attrs.pop("cn", None)
                await self._hierarchy.modify(
                    op_id,
                    modify_attrs,
                )

            await self._sync_link_operation_parameters(
                op_id=op_id,
                parameters=operation_params,
                replace=True,
            )

        if replace:
            for op_cn, existed in existing_by_cn.items():
                if op_cn not in desired_cns:
                    await self._hierarchy.delete(existed[0])

    async def _sync_link_operation_parameters(
        self, op_id: str, parameters: list[dict[str, Any]], replace: bool = True
    ) -> None:
        existing = await self._hierarchy.search(
            {
                "base": op_id,
                "scope": hierarchy.CN_SCOPE_ONELEVEL,
                "filter": {"objectClass": ["prsDatastorageTagOperationParameter"]},
                "attributes": ["cn", "prsActive", "prsJsonConfigString"],
                "deref": False,
            }
        )
        existing_by_cn = {item[2]["cn"][0]: item for item in (existing or [])}

        desired_cns = set()
        for p in parameters or []:
            p_attrs = self._attrs_dict(p)
            p_cn = p_attrs.get("cn")
            if not p_cn:
                continue
            desired_cns.add(p_cn)

            node_attrs = self._prepare_node_attrs(
                p_attrs,
                object_class="prsDatastorageTagOperationParameter",
                defaults={
                    "prsActive": True,
                    "prsJsonConfigString": {},
                },
            )
            node_attrs["cn"] = p_cn

            existed = existing_by_cn.get(p_cn)
            if not existed:
                await self._hierarchy.add(
                    base=op_id,
                    attribute_values=self._prepare_node_add_attrs(node_attrs),
                )
            else:
                modify_attrs = dict(node_attrs)
                modify_attrs.pop("objectClass", None)
                modify_attrs.pop("cn", None)
                await self._hierarchy.modify(
                    existed[0],
                    modify_attrs,
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
        if not isinstance(res, dict):
            self._logger.error(f"{self._config.svc_name} :: Некорректный ответ обработчика хранилища {datastorage_id}.")
            return

        get_tag = {"id": payload["tagId"], "attributes": ["prsValueTypeCode"]}
        tag_data = await self._hierarchy.search(payload=get_tag)
        if not tag_data:
            self._logger.error(f"{self._config.svc_name} :: Нет данных по тегу {payload['id']}.")
            return

        prs_store = res.get("prsStore")

        node_dn = await self._hierarchy.get_node_dn(payload["dataStorageId"])
        tags_node_id = await self._hierarchy.get_node_id(f"cn=tags,cn=system,{node_dn}")
        if not tags_node_id:
            system_node_id = await self._hierarchy.get_node_id(f"cn=system,{node_dn}")
            if not system_node_id:
                system_node_id = await self._hierarchy.add(
                    base=payload["dataStorageId"],
                    attribute_values={"cn": ["system"], "prsSystemNode": True},
                )
            tags_node_id = await self._hierarchy.add(
                base=system_node_id,
                attribute_values={"cn": ["tags"], "prsSystemNode": True},
            )

        link_attrs = payload.get("attributes") or {}
        link_entity_type = link_attrs.get("prsEntityTypeCode")
        tag_value_type = int(tag_data[0][2]["prsValueTypeCode"][0])
        link_cfg: dict[str, Any] | None = None
        if "prsJsonConfigString" in link_attrs:
            link_cfg = copy.deepcopy(link_attrs.get("prsJsonConfigString") or {})
            if tag_value_type != 5:
                link_cfg["prsValueTypeCode"] = tag_value_type
        else:
            # Как в v1: prsJsonConfigString с prsValueTypeCode нужен для _tag_updated в app (смена типа тега).
            link_cfg = {} if tag_value_type == 5 else {"prsValueTypeCode": tag_value_type}

        existing_link = await self._hierarchy.search(
            payload={
                "base": tags_node_id,
                "scope": hierarchy.CN_SCOPE_ONELEVEL,
                "filter": {"objectClass": ["prsDatastorageTagData"], "cn": [payload["tagId"]]},
                "attributes": ["cn"],
                "deref": False,
            }
        )
        link_id = existing_link[0][0] if existing_link else None

        attr_vals: dict[str, Any] = {}
        if link_cfg is not None and link_cfg:
            attr_vals["prsJsonConfigString"] = link_cfg
        if prs_store is not None:
            attr_vals["prsStore"] = prs_store
        if link_entity_type is not None:
            attr_vals["prsEntityTypeCode"] = int(link_entity_type)

        if link_id is None:
            create_vals = {"objectClass": ["prsDatastorageTagData"], "cn": payload["tagId"], **attr_vals}
            link_id = await self._hierarchy.add(base=tags_node_id, attribute_values=create_vals)
            await self._hierarchy.add_alias(
                parent_id=link_id,
                aliased_object_id=payload["tagId"],
                alias_name=payload["tagId"],
            )
        elif attr_vals:
            # Обновляем узел привязки только если действительно есть изменяемые атрибуты.
            # В противном случае modify с пустым словарём приведёт к ошибке
            # "Необходимо указать изменяемые атрибуты." в hierarchy.modify.
            await self._hierarchy.modify(link_id, attr_vals)

        if "operations" in payload:
            await self._sync_link_operations(
                link_id=link_id,
                operations=payload.get("operations") or [],
                replace=True,
            )

        self._logger.info(
            f"{self._config.svc_name} :: Тег {payload['tagId']} привязан к хранилищу {payload['dataStorageId']}"
        )


settings = DataStoragesModelCRUDV2Settings()
app = DataStoragesModelCRUDV2(settings=settings, title="DataStoragesModelCRUDV2")
