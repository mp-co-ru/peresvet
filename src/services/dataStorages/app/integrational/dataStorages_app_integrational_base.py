import sys
import json
import asyncio
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

sys.path.append(".")

from src.common.hierarchy import CN_SCOPE_ONELEVEL, CN_SCOPE_SUBTREE
import src.common.times as t
from src.services.dataStorages.app.dataStorages_app_base import DataStoragesAppBase
from src.services.dataStorages.app.integrational.dataStorages_app_integrational_utils import (
    OperationKind,
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
    - для тегов, привязанных к dataStorage типа 2, используется ссылка на LDAP-операции (GET/SET),
      а не таблица/метрика, создаваемая автоматически;
    - запись выполняется немедленно (SET), без кэширования в historian-таблицы.
    """

    _META_LINK_TTL_SEC = 30
    _META_OPERATION_TTL_SEC = 30
    _GET_MAX_ROWS_CAP = 50000
    _RE_OP_NAME = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")

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
        raise NotImplementedError("Для интеграционных хранилищ чтение выполняется через операции GET (dataStorage type=2).")

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
                msg = f"Ошибка чтения интеграционного тега '{tag_id}': {ex}"
                self._logger.error(f"{self._config.svc_name} :: {msg}")
                return {"error": {"code": 500, "message": msg}}

        return result

    async def _tag_set(self, mes: dict, routing_key: str | None = None) -> dict:
        for tag_item in mes.get("data") or []:
            tag_id = tag_item.get("tagId")
            if not tag_id:
                continue

            try:
                await self._write_integrational_points(tag_id=tag_id, tag_item=tag_item, request=mes)
            except Exception as ex:
                msg = f"Ошибка записи интеграционного тега '{tag_id}': {ex}"
                self._logger.error(f"{self._config.svc_name} :: {msg}")
                return {"error": {"code": 500, "message": msg}}
        return {}

    async def _link_tag(self, mes: dict, routing_key: str | None = None) -> dict | None:
        """Привязка тега к интеграционному хранилищу: без создания таблиц."""
        tag_id = mes["tagId"]
        ds_id = mes["dataStorageId"]

        if ds_id not in self._connection_pools:
            self._logger.error(f"{self._config.svc_name} :: Хранилища {ds_id} нет в списке поддерживаемых.")
            return {"prsStore": None}

        cache = self._cache
        assert cache is not None
        await self._bind_tag(tag_id, True)
        async with cache.get_redis() as r:
            await r.json().arrappend(f"{ds_id}.{self._config.svc_name}", "tags", tag_id)  # type: ignore[reportGeneralTypeIssues]
        await self._invalidate_meta_cache_for_tag(tag_id)

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
        await self._invalidate_meta_cache_for_tag(tag_id)

    async def _link_alert(self, mes: dict, routing_key: str | None = None) -> dict:
        raise NotImplementedError("Интеграционные хранилища не поддерживают alerts в текущей реализации.")

    async def _unlink_alert(self, mes: dict, routing_key: str | None = None) -> None:
        raise NotImplementedError("Интеграционные хранилища не поддерживают alerts в текущей реализации.")

    async def _tag_updated(self, mes: dict, routing_key: str = None):
        await self._invalidate_meta_cache_for_tag(mes["id"])

    async def _tag_deleted(self, mes: dict, routing_key: str = None):
        await self._invalidate_meta_cache_for_tag(mes["id"])
        await super()._tag_deleted(mes=mes, routing_key=routing_key)

    async def updating(self, mes: dict, routing_key: str = None) -> None:
        await super().updating(mes=mes, routing_key=routing_key)
        await self._invalidate_meta_cache()

    async def _read_integrational_points(self, tag_id: str, request: dict) -> list[tuple]:
        ds_id, link_id, _link = await self._resolve_integrational_link(tag_id=tag_id)
        request_params = request.get("params") if isinstance(request.get("params"), dict) else {}
        op_name = self._normalize_operation_name(request_params.get("operation"))
        op_cn = await self._resolve_operation_cn_from_link(
            link_id=link_id,
            requested_operation=op_name,
            expected_kind=OperationKind.GET,
        )

        op = await self._load_operation_from_link(
            tag_id=tag_id,
            link_id=link_id,
            op_cn=op_cn,
            expected_kind=OperationKind.GET,
        )

        ctx = self._build_eval_context(request=request, tag_id=tag_id)
        param_values = await self._eval_params_jsonata(op=op, context=ctx)

        return await self._execute_get(
            ds_id=ds_id,
            op=op,
            param_values=param_values,
            request=request,
        )

    async def _write_integrational_points(self, tag_id: str, tag_item: dict, request: dict) -> None:
        ds_id, link_id, _link = await self._resolve_integrational_link(tag_id=tag_id)
        request_params = request.get("params") if isinstance(request.get("params"), dict) else {}
        op_name = self._normalize_operation_name(request_params.get("operation"))
        op_cn = await self._resolve_operation_cn_from_link(
            link_id=link_id,
            requested_operation=op_name,
            expected_kind=OperationKind.SET,
        )
        op = await self._load_operation_from_link(
            tag_id=tag_id,
            link_id=link_id,
            op_cn=op_cn,
            expected_kind=OperationKind.SET,
        )

        points = tag_item.get("data") or []
        if not points and request_params:
            points = [None]

        for point in points:
            if isinstance(point, (tuple, list)):
                x = point[0] if len(point) > 0 else None
                y = point[1] if len(point) > 1 else None
                q = point[2] if len(point) > 2 else None
            else:
                y = None
                x = None
                q = None

            ctx = self._build_eval_context(
                request=request,
                tag_id=tag_id,
                tag_item=tag_item,
                points=points,
                point=point,
                y=y,
                x=x,
                q=q,
            )

            param_values = await self._eval_params_jsonata(op=op, context=ctx)
            await self._execute_set(ds_id=ds_id, op=op, param_values=param_values)

    async def _resolve_integrational_link(self, tag_id: str) -> tuple[str, str, dict]:
        """Находит dataStorage и LDAP-конфиг привязки для интеграционного тега."""
        cache_key = self._meta_cache_key("link", tag_id)
        cached = await self._meta_cache_get(cache_key)
        if cached:
            cached_ds_id = cached.get("ds_id")
            cached_link_id = cached.get("link_id")
            if cached_ds_id in self._connection_pools and isinstance(cached_link_id, str):
                return cached_ds_id, cached_link_id, cached["attrs"]
            await self._invalidate_meta_cache_for_tag(tag_id)

        discovered_ids: list[str] = []
        try:
            discovered_ids = await DataStoragesAppIntegrationalBase._discover_supported_ds_ids(self)
        except Exception:
            discovered_ids = []

        # Ensure newly created/updated supported dataStorages are pulled into runtime pools.
        add_supported = getattr(self, "_add_supported_ds", None)
        if callable(add_supported):
            for ds_id in discovered_ids:
                if ds_id in self._connection_pools:
                    continue
                try:
                    await add_supported(ds_id)
                except Exception:
                    # Keep lookup resilient: if add/pool creation failed,
                    # we still try to resolve link directly from hierarchy.
                    pass

        candidate_ds_ids: list[str] = []
        for ds_id in list(self._connection_pools.keys()) + discovered_ids:
            if ds_id not in candidate_ds_ids:
                candidate_ds_ids.append(ds_id)

        for ds_id in candidate_ds_ids:

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
            # Fast path: query already filtered by cn=<tag_id>, so any active result is a valid link.
            if res:
                for link_id, _, attrs in res:
                    if not self._is_ldap_active(attrs):
                        continue
                    await self._meta_cache_set(
                        cache_key,
                        {"ds_id": ds_id, "link_id": link_id, "attrs": attrs},
                        self._META_LINK_TTL_SEC,
                    )
                    return ds_id, link_id, attrs

            # Fallback: support non-standard link CN with alias child cn=<tag_id>.
            match = await self._pick_matching_link(tag_id=tag_id, ds_id=ds_id, direct_res=None)
            if not match:
                continue
            link_id, attrs = match
            await self._meta_cache_set(
                cache_key,
                {"ds_id": ds_id, "link_id": link_id, "attrs": attrs},
                self._META_LINK_TTL_SEC,
            )
            return ds_id, link_id, attrs

        raise ValueError("Интеграционная привязка тега к хранилищу не найдена.")

    async def _discover_supported_ds_ids(self) -> list[str]:
        configured_reader = getattr(self, "_configured_ds_ids", None)
        if callable(configured_reader):
            configured = configured_reader()
        else:
            cfg_nodes = getattr(self._config, "nodes", None)
            if isinstance(cfg_nodes, list) and cfg_nodes:
                configured = [str(x) for x in cfg_nodes if x]
            else:
                legacy = getattr(self._config, "datastorages_id", None)
                configured = [str(x) for x in legacy if x] if isinstance(legacy, list) and legacy else []
        if configured:
            return configured

        ds_root_id = await self._hierarchy.get_node_id("cn=dataStorages,cn=prs")
        if not ds_root_id:
            return []
        items = await self._hierarchy.search(
            payload={
                "base": ds_root_id,
                "scope": CN_SCOPE_ONELEVEL,
                "filter": {
                    "objectClass": ["prsDataStorage"],
                    "prsEntityTypeCode": [self._config.datastorage_type],
                },
                "attributes": ["cn"],
                "deref": False,
            }
        )
        return [item[0] for item in (items or [])]

    async def _pick_matching_link(self, tag_id: str, ds_id: str, direct_res: list | None) -> tuple[str, dict] | None:
        """Return matching link node by cn/tag alias under one dataStorage subtree."""
        candidates = direct_res or []
        if not candidates:
            candidates = await self._hierarchy.search(
                payload={
                    "base": ds_id,
                    "scope": CN_SCOPE_SUBTREE,
                    "filter": {"objectClass": ["prsDatastorageTagData"]},
                    "deref": False,
                    "attributes": ["cn", "prsActive", "prsEntityTypeCode", "prsJsonConfigString"],
                }
            ) or []

        for link_id, _, attrs in candidates:
            if not self._is_ldap_active(attrs):
                continue
            cn_list = attrs.get("cn") or []
            if cn_list and cn_list[0] == tag_id:
                return link_id, attrs

            # Fallback for links with custom CN: accept alias child cn=<tag_id>.
            alias = await self._hierarchy.search(
                payload={
                    "base": link_id,
                    "scope": CN_SCOPE_SUBTREE,
                    "filter": {"cn": [tag_id]},
                    "deref": False,
                    "attributes": ["cn"],
                }
            )
            if alias:
                return link_id, attrs
        return None

    async def _load_operation_from_link(
            self,
            tag_id: str,
            link_id: str,
            op_cn: str,
            expected_kind: OperationKind,
        ) -> OperationDef:
        cache_key = self._meta_cache_key("op", tag_id, op_cn)
        cached = await self._meta_cache_get(cache_key)
        if cached:
            if "kind" in cached:
                try:
                    cached["kind"] = OperationKind(int(cached["kind"]))
                except Exception:
                    cached["kind"] = expected_kind
            return OperationDef(**cached)

        found = await self._hierarchy.search(
            payload={
                "base": link_id,
                "scope": CN_SCOPE_SUBTREE,
                "filter": {"objectClass": ["prsDatastorageTagOperation"], "cn": [op_cn]},
                "attributes": ["cn", "prsActive", "prsEntityTypeCode", "prsJsonConfigString"],
                "deref": False,
            }
        )
        if not found:
            raise ValueError(f"Операция '{op_cn}' не найдена в дочерних узлах link.")

        op_id, _, op_attrs = found[0]
        active = self._is_ldap_active(op_attrs)
        if not bool(active):
            raise ValueError(f"Операция '{op_cn}' неактивна.")

        kind = OperationKind(self._operation_kind_code(op_attrs))
        if kind != expected_kind:
            raise ValueError(
                f"Операция '{op_cn}' имеет тип '{int(kind)}', ожидается '{int(expected_kind)}'."
            )

        cfg = self._safe_json_loads(op_attrs.get("prsJsonConfigString")) or {}
        query = cfg.get("query")
        if not query:
            raise ValueError(f"У операции '{op_cn}' нет ключа query.")

        validate_sql(query, kind)

        timeout_ms = cfg.get("timeoutMs")
        max_rows = cfg.get("maxRows")
        version = cfg.get("version")

        param_specs: dict[str, dict] = {}
        params = await self._hierarchy.search(
            payload={
                "base": op_id,
                "scope": CN_SCOPE_SUBTREE,
                "filter": {"objectClass": ["prsDatastorageTagOperationParameter"]},
                "attributes": ["cn", "prsActive", "prsJsonConfigString"],
                "deref": False,
            }
        )
        for _, __, p_attrs in params or []:
            p_cn_list = p_attrs.get("cn")
            if not p_cn_list:
                continue
            p_cn = p_cn_list[0]
            p_active = self._is_ldap_active(p_attrs)
            if not bool(p_active):
                continue
            p_cfg = self._safe_json_loads(p_attrs.get("prsJsonConfigString")) or {}
            if not isinstance(p_cfg, dict):
                raise ValueError(f"Некорректный prsJsonConfigString у параметра '{p_cn}'.")
            param_specs[p_cn] = p_cfg

        op = OperationDef(
            id=op_id,
            cn=op_cn,
            kind=kind,
            active=bool(active),
            query=query,
            timeout_ms=int(timeout_ms) if timeout_ms is not None else None,
            max_rows=int(max_rows) if max_rows is not None else None,
            version=int(version) if version is not None else None,
            parameters=param_specs,
        )
        await self._meta_cache_set(cache_key, self._operation_to_cache_payload(op), self._META_OPERATION_TTL_SEC)
        return op

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

    async def _eval_params_jsonata(self, op: OperationDef, context: dict) -> dict[str, Any]:
        sql, needed_params = rewrite_named_params(op.query)
        # rewrite_named_params нам нужен только для списка параметров
        _ = sql

        values: dict[str, Any] = {}
        for name in needed_params:
            spec = op.parameters.get(name) or {}
            expr = spec.get("JSONata")
            if not isinstance(expr, str) or not expr.strip():
                raise ValueError(
                    f"Для параметра '{name}' отсутствует prsJsonConfigString.JSONata "
                    f"в описании операции '{op.cn}'."
                )
            values[name] = await self._jsonata_eval(expr, context, timeout_ms=op.timeout_ms)
            if values[name] is None:
                raise ValueError(
                    f"Параметр '{name}' не извлечён из пользовательского запроса "
                    f"(JSONata вернул null) для операции '{op.cn}'."
                )

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

    async def _execute_get(
            self,
            ds_id: str,
            op: OperationDef,
            param_values: dict[str, Any],
            request: dict | None = None,
        ) -> list[tuple]:
        sql, param_names = rewrite_named_params(op.query)
        args = [param_values.get(name) for name in param_names]

        query = sql
        limit = self._GET_MAX_ROWS_CAP
        if op.max_rows is not None:
            limit = min(limit, int(op.max_rows))
        req_params = request.get("params") if isinstance((request or {}).get("params"), dict) else {}
        if req_params:
            req_limit = req_params.get("limit")
            if isinstance(req_limit, int) and req_limit > 0:
                limit = min(limit, req_limit)
        query = f"select * from ({sql}) as sub limit {int(limit)}"

        rows = await self._db_fetch(ds_id=ds_id, query=query, args=args, timeout_ms=op.timeout_ms)
        if not rows:
            return []

        first = self._row_to_dict(rows[0])
        cols = {str(c).lower() for c in first.keys()}

        all_records_as_value = self._coerce_bool(req_params.get("allRecordsAsValue"), default=True)
        finish_ts = self._resolve_finish_ts(request=request)

        if all_records_as_value:
            values = [self._row_to_dict(r) for r in rows]
            return [(finish_ts, values, 0)]

        result: list[tuple] = []
        has_x = "x" in cols
        has_q = "q" in cols
        has_y = "y" in cols
        for r in rows:
            rec = self._row_to_dict(r)
            x = self._row_get_case_insensitive(rec, "x") if has_x else finish_ts
            q = self._row_get_case_insensitive(rec, "q") if has_q else 0
            if has_y:
                y = self._row_get_case_insensitive(rec, "y")
            else:
                y = self._row_without_case_insensitive(rec, {"x", "q"})
                if not y:
                    y = rec
            if q is None:
                q = 0
            result.append((x, y, q))
        return result

    async def _execute_set(self, ds_id: str, op: OperationDef, param_values: dict[str, Any]) -> None:
        sql, param_names = rewrite_named_params(op.query)
        args = [param_values.get(name) for name in param_names]
        await self._db_execute(ds_id=ds_id, query=sql, args=args, timeout_ms=op.timeout_ms)

    @abstractmethod
    async def _db_fetch(self, ds_id: str, query: str, args: list[Any], timeout_ms: int | None) -> list[Any]:
        """Выполнить SELECT и вернуть список записей (Record-подобных)."""

    @abstractmethod
    async def _db_execute(self, ds_id: str, query: str, args: list[Any], timeout_ms: int | None) -> None:
        """Выполнить INSERT/UPDATE/DELETE."""

    async def _meta_cache_get(self, key: str) -> dict | None:
        async with self._cache.get_redis() as r:
            raw = await r.get(key)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            return json.loads(raw)
        except Exception:
            return None

    async def _meta_cache_set(self, key: str, data: dict, ttl_sec: int) -> None:
        async with self._cache.get_redis() as r:
            await r.set(key, json.dumps(data), ex=ttl_sec)

    async def _invalidate_meta_cache(self, pattern_suffix: str = "*") -> None:
        pattern = self._meta_cache_key(pattern_suffix)
        async with self._cache.get_redis() as r:
            keys = []
            async for key in r.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                await r.delete(*keys)

    async def _invalidate_meta_cache_for_tag(self, tag_id: str) -> None:
        await self._invalidate_meta_cache(f"link:{tag_id}")

    def _meta_cache_key(self, *parts: Any) -> str:
        suffix = ":".join(str(p) for p in parts)
        return f"meta:{self._config.svc_name}:{suffix}"

    def _operation_to_cache_payload(self, op: OperationDef) -> dict[str, Any]:
        return {
            "id": op.id,
            "cn": op.cn,
            "kind": int(op.kind),
            "active": op.active,
            "query": op.query,
            "timeout_ms": op.timeout_ms,
            "max_rows": op.max_rows,
            "version": op.version,
            "parameters": op.parameters,
        }

    def _normalize_operation_name(self, operation: Any) -> str | None:
        if operation is None:
            return None
        if not isinstance(operation, str):
            raise ValueError("params.operation должен быть строкой.")
        op = operation.strip()
        if not op:
            return None
        return op

    async def _resolve_operation_cn_from_link(
            self,
            link_id: str,
            requested_operation: str | None,
            expected_kind: OperationKind,
        ) -> str:
        operations = await self._hierarchy.search(
            payload={
                "base": link_id,
                "scope": CN_SCOPE_SUBTREE,
                "filter": {"objectClass": ["prsDatastorageTagOperation"]},
                "attributes": ["cn", "prsEntityTypeCode"],
                "deref": False,
            }
        )
        if not operations:
            raise ValueError("У привязки тега не найдено ни одной операции.")

        if requested_operation:
            for _, __, attrs in operations:
                cn_list = attrs.get("cn")
                if not cn_list:
                    continue
                cn = cn_list[0]
                if cn == requested_operation:
                    kind = OperationKind(self._operation_kind_code(attrs))
                    if kind != expected_kind:
                        raise ValueError(
                            f"Операция '{requested_operation}' имеет тип '{int(kind)}', "
                            f"ожидается '{int(expected_kind)}'."
                        )
                    return cn
            raise ValueError(f"Операция '{requested_operation}' не найдена среди дочерних узлов link.")

        for _, __, attrs in operations:
            cn_list = attrs.get("cn")
            if not cn_list:
                continue
            cn = cn_list[0]
            kind = OperationKind(self._operation_kind_code(attrs))
            if kind == expected_kind:
                return cn

        raise ValueError(
            f"Не найдена операция нужного типа ({int(expected_kind)}) среди дочерних узлов link."
        )

    def _extract_operation_cn(self, value: Any) -> str | None:
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            cn = value.get("operationCn")
            if isinstance(cn, str):
                return cn
        return None

    def _operation_kind_code(self, operation_cfg: dict) -> int:
        raw = operation_cfg.get("prsEntityTypeCode", 0)
        if isinstance(raw, list):
            raw = raw[0] if raw else 0
        try:
            code = int(raw)
        except Exception as ex:
            raise ValueError(f"Некорректный prsEntityTypeCode у операции: {raw}") from ex
        if code not in (0, 1):
            raise ValueError(f"Недопустимый prsEntityTypeCode у операции: {code}. Ожидается 0 или 1.")
        return code

    def _is_ldap_active(self, attrs: dict, default: bool = True) -> bool:
        raw = attrs.get("prsActive")
        if isinstance(raw, list):
            raw = raw[0] if raw else None
        if raw is None:
            return default
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.strip().upper() == "TRUE"
        return default

    def _build_eval_context(
            self,
            request: dict,
            tag_id: str,
            tag_item: dict | None = None,
            points: list | None = None,
            point: Any = None,
            y: Any = None,
            x: Any = None,
            q: Any = None,
        ) -> dict[str, Any]:
        params = request.get("params") if isinstance(request.get("params"), dict) else {}
        ctx = dict(request)
        ctx["request"] = request
        ctx["params"] = params
        ctx["currentTagId"] = tag_id
        ctx["tagId"] = tag_id
        if tag_item is not None:
            ctx["tagItem"] = tag_item
        if points is not None:
            ctx["data"] = points
        point_obj = {"y": y, "x": x, "q": q, "raw": point}
        ctx["point"] = point_obj
        ctx["y"] = y
        ctx["x"] = x
        ctx["q"] = q
        return ctx

    def _row_to_dict(self, row: Any) -> dict[str, Any]:
        if isinstance(row, dict):
            return dict(row)
        if hasattr(row, "items"):
            return {str(k): v for k, v in row.items()}
        keys = row.keys() if hasattr(row, "keys") else []
        return {str(k): row.get(k) for k in keys}

    def _row_get_case_insensitive(self, row: dict[str, Any], key: str) -> Any:
        key_l = key.lower()
        for k, v in row.items():
            if str(k).lower() == key_l:
                return v
        return None

    def _row_without_case_insensitive(self, row: dict[str, Any], excluded: set[str]) -> dict[str, Any]:
        excluded_l = {x.lower() for x in excluded}
        return {k: v for k, v in row.items() if str(k).lower() not in excluded_l}

    def _resolve_finish_ts(self, request: dict | None) -> int:
        if not request:
            return t.ts(None)
        finish = request.get("finish")
        if finish is None:
            return t.ts(None)
        return t.ts(finish)

    def _coerce_bool(self, value: Any, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            v = value.strip().lower()
            if v in ("true", "1", "yes", "on"):
                return True
            if v in ("false", "0", "no", "off"):
                return False
        raise ValueError("params.allRecordsAsValue должен быть bool.")

