import sys
import json
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

sys.path.append(".")

from src.common.hierarchy import CN_SCOPE_ONELEVEL, CN_SCOPE_SUBTREE
from src.services.dataStorages.app.dataStorages_app_base import DataStoragesAppBase
from src.services.dataStorages.app.integrational.dataStorages_app_integrational_utils import (
    OperationKind,
    ensure_columns_xyq,
    rewrite_named_params,
    validate_sql,
)


@dataclass(frozen=True)
class OperationDef:
    id: str
    cn: str
    kind: OperationKind
    active: bool
    query: str
    timeout_ms: int | None
    max_rows: int | None
    version: int | None
    parameters: dict[str, dict]


class DataStoragesAppIntegrationalBase(DataStoragesAppBase, ABC):
    """Базовый класс интеграционных хранилищ.

    Отличия от исторических хранилищ:
    - для тегов с prsEntityTypeCode=2 используется ссылка на LDAP-операции (GET/SET),
      а не таблица/метрика, создаваемая автоматически;
    - запись выполняется немедленно (SET), без кэширования в historian-таблицы.
    """

    # код типа привязки тега к хранилищу: 2 = интеграционный тег
    _LINK_ENTITY_TYPE_INTEGRATIONAL = 2

    async def _write_cache_data(self, tag_ids: list[str] | None = None) -> None:
        # интеграционные теги не используют сброс historian-кэша
        return

    async def _write_tag_data_to_db(self, tag_id: str) -> None:
        # интеграционные теги не пишут точки в historian-таблицы
        return

    # ---------------------------------------------------------------------
    # DataStoragesAppBase abstract methods (not used for integrational tags)
    # ---------------------------------------------------------------------

    async def _create_store_name_for_new_tag(self, ds_id: str, tag_id: str) -> dict | None:
        # Integrational tags do not create per-tag stores/tables.
        return None

    async def _create_store_for_tag(self, tag_id: str, ds_id: str, store: dict) -> None:
        # Integrational tags do not create stores.
        return

    async def _create_store_name_for_new_alert(self, ds_id: str, alert_id: str) -> dict | None:
        raise NotImplementedError("Интеграционные хранилища не поддерживают alerts в текущей реализации.")

    async def _create_store_for_alert(self, alert_id: str, ds_id: str, store: dict) -> None:
        raise NotImplementedError("Интеграционные хранилища не поддерживают alerts в текущей реализации.")

    async def _read_data(
        self,
        tag_id: str,
        start: int,
        finish: int,
        order: int,
        count: int,
        one_before: bool,
        one_after: bool,
        value: Any = None,
    ):
        # Historical read path is not used for integrational tags; `prsTag.app.data_get.*`
        # is handled by `_tag_get()` override above.
        raise NotImplementedError("Для интеграционных хранилищ чтение выполняется через операции GET (prsEntityTypeCode=2).")

    async def _tag_get(self, mes: dict, routing_key: str | None = None) -> dict:
        result = {"data": []}
        tag_ids = mes.get("tagId") or []
        for tag_id in tag_ids:
            try:
                points = await self._read_integrational_points(tag_id=tag_id, request=mes)
                excess = False
                max_count = mes.get("maxCount")
                if max_count is not None:
                    excess = len(points) > max_count
                    if max_count == 0:
                        points = []
                    elif max_count == 1:
                        points = points[:1]
                    elif max_count == 2:
                        points = [points[0], points[-1]] if points else []
                    else:
                        points = points[: max_count - 1] + [points[-1]] if points else []

                item = {"tagId": tag_id, "data": points}
                if max_count is not None:
                    item["excess"] = excess
                result["data"].append(item)
            except Exception as ex:
                self._logger.error(f"{self._config.svc_name} :: Ошибка чтения интеграционного тега '{tag_id}': {ex}")

        return result

    async def _tag_set(self, mes: dict, routing_key: str | None = None) -> None:
        for tag_item in mes.get("data") or []:
            tag_id = tag_item.get("tagId")
            if not tag_id:
                continue

            try:
                await self._write_integrational_points(tag_id=tag_id, tag_item=tag_item, request=mes)
            except Exception as ex:
                self._logger.error(f"{self._config.svc_name} :: Ошибка записи интеграционного тега '{tag_id}': {ex}")

    async def _link_tag(self, mes: dict, routing_key: str | None = None) -> dict | None:
        """Привязка тега к интеграционному хранилищу: без создания таблиц."""
        tag_id = mes["tagId"]
        ds_id = mes["dataStorageId"]

        if ds_id not in self._connection_pools:
            self._logger.error(f"{self._config.svc_name} :: Хранилища {ds_id} нет в списке поддерживаемых.")
            return {"prsStore": None}

        await self._bind_tag(tag_id, True)
        cache = self._cache
        assert cache is not None
        async with cache.get_redis() as r:
            await r.json().arrappend(f"{ds_id}.{self._config.svc_name}", "tags", tag_id)  # type: ignore[reportGeneralTypeIssues]

        return {"prsStore": None}

    async def _unlink_tag(self, mes: dict, routing_key: str | None = None) -> None:
        tag_id = mes["tagId"]
        ds_id = mes["dataStorageId"]

        await self._bind_tag(tag_id, False)
        cache = self._cache
        assert cache is not None
        async with cache.get_redis() as r:
            index = await r.json().arrindex(f"{ds_id}.{self._config.svc_name}", "tags", tag_id)  # type: ignore[reportGeneralTypeIssues]
            if index > -1:
                await r.json().arrpop(f"{ds_id}.{self._config.svc_name}", "tags", index[0])  # type: ignore[reportGeneralTypeIssues]

    async def _link_alert(self, mes: dict, routing_key: str | None = None) -> dict:
        raise NotImplementedError("Интеграционные хранилища не поддерживают alerts в текущей реализации.")

    async def _unlink_alert(self, mes: dict, routing_key: str | None = None) -> None:
        raise NotImplementedError("Интеграционные хранилища не поддерживают alerts в текущей реализации.")

    async def _read_integrational_points(self, tag_id: str, request: dict) -> list[tuple]:
        ds_id, link = await self._resolve_integrational_link(tag_id=tag_id)

        link_cfg = self._safe_json_loads(link.get("prsJsonConfigString"))
        get_cfg = (link_cfg or {}).get("get") or {}
        op_cn = get_cfg.get("operationCn")
        if not op_cn:
            raise ValueError("Не указан get.operationCn в конфигурации привязки.")

        op = await self._load_operation(ds_id=ds_id, op_cn=op_cn, expected_kind=OperationKind.GET)

        ctx = dict(request)
        ctx["currentTagId"] = tag_id
        param_exprs = get_cfg.get("params") or {}
        param_values = await self._eval_params_jsonata(param_exprs, op, ctx)

        return await self._execute_get(ds_id=ds_id, op=op, param_values=param_values)

    async def _write_integrational_points(self, tag_id: str, tag_item: dict, request: dict) -> None:
        ds_id, link = await self._resolve_integrational_link(tag_id=tag_id)

        link_cfg = self._safe_json_loads(link.get("prsJsonConfigString"))
        set_cfg = (link_cfg or {}).get("set") or {}
        op_cn = set_cfg.get("operationCn")
        if not op_cn:
            raise ValueError("Не указан set.operationCn в конфигурации привязки.")

        op = await self._load_operation(ds_id=ds_id, op_cn=op_cn, expected_kind=OperationKind.SET)

        points = tag_item.get("data") or []
        for point in points:
            # Point contract: [x, y, q]
            x = point[0] if len(point) > 0 else None
            y = point[1] if len(point) > 1 else None
            q = point[2] if len(point) > 2 else None

            ctx = {
                "request": request,
                "tagId": tag_id,
                "data": points,
                "point": {"y": y, "x": x, "q": q},
                "y": y,
                "x": x,
                "q": q,
            }

            param_exprs = set_cfg.get("params") or {}
            param_values = await self._eval_params_jsonata(param_exprs, op, ctx)
            await self._execute_set(ds_id=ds_id, op=op, param_values=param_values)

    async def _resolve_integrational_link(self, tag_id: str) -> tuple[str, dict]:
        """Находит dataStorage и LDAP-конфиг привязки для интеграционного тега."""
        for ds_id in self._connection_pools.keys():
            cache = self._cache
            assert cache is not None
            async with cache.get_redis() as r:
                ds_active = await r.json().get(f"{ds_id}.{self._config.svc_name}", "prsActive")  # type: ignore[reportGeneralTypeIssues]
            if ds_active is False:
                continue

            res = await self._hierarchy.search(
                payload={
                    "base": ds_id,
                    "scope": CN_SCOPE_SUBTREE,
                    "filter": {
                        "objectClass": ["prsDatastorageTagData"],
                        "cn": [tag_id],
                    },
                    "deref": False,
                    "attributes": ["prsActive", "prsEntityTypeCode", "prsJsonConfigString"],
                }
            )
            if not res:
                continue

            attrs = res[0][2]
            if attrs.get("prsActive", ["TRUE"])[0] != "TRUE":
                continue

            entity_type = attrs.get("prsEntityTypeCode")
            if not entity_type:
                raise ValueError("Не задан prsEntityTypeCode у привязки тега к хранилищу.")
            if int(entity_type[0]) != self._LINK_ENTITY_TYPE_INTEGRATIONAL:
                raise ValueError(f"Привязка тега не является интеграционной (prsEntityTypeCode != 2).")

            return ds_id, attrs

        raise ValueError("Интеграционная привязка тега к хранилищу не найдена.")

    async def _load_operation(self, ds_id: str, op_cn: str, expected_kind: OperationKind) -> OperationDef:
        op_nodes = await self._hierarchy.search(
            payload={
                "base": ds_id,
                "scope": CN_SCOPE_SUBTREE,
                "filter": {"objectClass": ["prsDatastorageOperation"], "cn": [op_cn]},
                "deref": False,
                "attributes": ["cn", "prsActive", "prsEntityTypeCode", "prsJsonConfigString"],
            }
        )
        if not op_nodes:
            raise ValueError(f"Операция '{op_cn}' не найдена.")

        op_id, _, attrs = op_nodes[0]
        active = attrs.get("prsActive", ["TRUE"])[0] == "TRUE"
        if not active:
            raise ValueError(f"Операция '{op_cn}' неактивна.")

        kind = OperationKind(int(attrs.get("prsEntityTypeCode", ["0"])[0]))
        if kind != expected_kind:
            raise ValueError(f"Операция '{op_cn}' имеет неверный тип (prsEntityTypeCode={int(kind)}).")

        cfg = self._safe_json_loads(attrs.get("prsJsonConfigString"))
        query = (cfg or {}).get("query")
        if not query:
            raise ValueError(f"У операции '{op_cn}' нет ключа query.")

        validate_sql(query, kind)

        timeout_ms = (cfg or {}).get("prsTimeOutMs")
        max_rows = (cfg or {}).get("prsMaxRows")
        version = (cfg or {}).get("prsVersion")

        params = await self._hierarchy.search(
            payload={
                "base": op_id,
                "scope": CN_SCOPE_ONELEVEL,
                "filter": {"objectClass": ["prsDatastorageOperationParameter"]},
                "deref": False,
                "attributes": ["cn", "prsActive", "prsJsonConfigString"],
            }
        )
        param_specs: dict[str, dict] = {}
        for p in params or []:
            p_cn = p[2]["cn"][0]
            p_active = p[2].get("prsActive", ["TRUE"])[0] == "TRUE"
            if not p_active:
                continue
            param_specs[p_cn] = self._safe_json_loads(p[2].get("prsJsonConfigString")) or {}

        return OperationDef(
            id=op_id,
            cn=op_cn,
            kind=kind,
            active=active,
            query=query,
            timeout_ms=int(timeout_ms) if timeout_ms is not None else None,
            max_rows=int(max_rows) if max_rows is not None else None,
            version=int(version) if version is not None else None,
            parameters=param_specs,
        )

    def _safe_json_loads(self, ldap_attr: Any) -> dict | None:
        if not ldap_attr:
            return None
        # Hierarchy.search возвращает dict[attr] = [str]
        if isinstance(ldap_attr, list):
            if not ldap_attr:
                return None
            s = ldap_attr[0]
        else:
            s = ldap_attr
        if s is None:
            return None
        if isinstance(s, dict):
            return s
        return json.loads(s)

    async def _eval_params_jsonata(self, param_exprs: dict, op: OperationDef, context: dict) -> dict[str, Any]:
        sql, needed_params = rewrite_named_params(op.query)
        # rewrite_named_params нам нужен только для списка параметров
        _ = sql

        values: dict[str, Any] = {}
        for name in needed_params:
            expr = param_exprs.get(name)
            spec = op.parameters.get(name) or {}

            if expr is None:
                if "default" in spec:
                    values[name] = spec["default"]
                    continue
                if spec.get("required", True):
                    raise ValueError(f"Для параметра '{name}' не задано выражение JSONata и нет default.")
                values[name] = None
                continue

            values[name] = await self._jsonata_eval(expr, context, timeout_ms=op.timeout_ms)

        return values

    async def _jsonata_eval(self, expr: str, data: dict, timeout_ms: int | None) -> Any:
        try:
            import jsonatapy  # type: ignore[reportMissingImports]
        except ModuleNotFoundError as ex:
            raise ModuleNotFoundError(
                "Не установлен пакет 'jsonatapy' (нужен для JSONata выражений)."
            ) from ex

        async def run():
            return await asyncio.to_thread(jsonatapy.evaluate, expr, data)

        if timeout_ms is None:
            return await run()
        return await asyncio.wait_for(run(), timeout=timeout_ms / 1000)

    async def _execute_get(self, ds_id: str, op: OperationDef, param_values: dict[str, Any]) -> list[tuple]:
        sql, param_names = rewrite_named_params(op.query)
        args = [param_values.get(name) for name in param_names]

        query = sql
        if op.max_rows is not None:
            query = f"select x, y, q from ({sql}) as sub limit {int(op.max_rows)}"

        rows = await self._db_fetch(ds_id=ds_id, query=query, args=args, timeout_ms=op.timeout_ms)
        if not rows:
            return []

        ensure_columns_xyq(rows[0].keys())
        return [(r.get("x"), r.get("y"), r.get("q")) for r in rows]

    async def _execute_set(self, ds_id: str, op: OperationDef, param_values: dict[str, Any]) -> None:
        sql, param_names = rewrite_named_params(op.query)
        args = [param_values.get(name) for name in param_names]
        await self._db_execute(ds_id=ds_id, query=sql, args=args, timeout_ms=op.timeout_ms)

    @abstractmethod
    async def _db_fetch(self, ds_id: str, query: str, args: list[Any], timeout_ms: int | None) -> list[Any]:
        """Выполнить SELECT и вернуть список записей (Record-подобных)."""

    @abstractmethod
    async def _db_execute(self, ds_id: str, query: str, args: list[Any], timeout_ms: int | None) -> None:
        """Выполнить INSERT/UPDATE."""

