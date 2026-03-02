import sys
import json
import asyncio
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

sys.path.append(".")

from src.common.hierarchy import CN_SCOPE_SUBTREE
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
    - для тегов с prsEntityTypeCode=2 используется ссылка на LDAP-операции (GET/SET),
      а не таблица/метрика, создаваемая автоматически;
    - запись выполняется немедленно (SET), без кэширования в historian-таблицы.
    """

    # код типа привязки тега к хранилищу: 2 = интеграционный тег
    _LINK_ENTITY_TYPE_INTEGRATIONAL = 2
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
        ds_id, link = await self._resolve_integrational_link(tag_id=tag_id)

        link_cfg = self._safe_json_loads(link.get("prsJsonConfigString"))
        get_cfg = (link_cfg or {}).get("get") or {}
        op_cn = get_cfg.get("operationCn")
        if not op_cn:
            raise ValueError("Не указан get.operationCn в конфигурации привязки.")

        op = await self._load_operation_from_link(
            tag_id=tag_id,
            link_cfg=link_cfg or {},
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
        ds_id, link = await self._resolve_integrational_link(tag_id=tag_id)

        link_cfg = self._safe_json_loads(link.get("prsJsonConfigString"))
        set_cfg = (link_cfg or {}).get("set") or {}
        request_params = request.get("params") if isinstance(request.get("params"), dict) else {}
        op_name = self._normalize_operation_name(request_params.get("operation"))
        op_cn = self._resolve_set_operation_cn(set_cfg=set_cfg, requested_operation=op_name)
        op = await self._load_operation_from_link(
            tag_id=tag_id,
            link_cfg=link_cfg or {},
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

    async def _resolve_integrational_link(self, tag_id: str) -> tuple[str, dict]:
        """Находит dataStorage и LDAP-конфиг привязки для интеграционного тега."""
        cache_key = self._meta_cache_key("link", tag_id)
        cached = await self._meta_cache_get(cache_key)
        if cached:
            cached_ds_id = cached.get("ds_id")
            if cached_ds_id in self._connection_pools:
                return cached_ds_id, cached["attrs"]
            await self._invalidate_meta_cache_for_tag(tag_id)

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

            await self._meta_cache_set(
                cache_key,
                {"ds_id": ds_id, "attrs": attrs},
                self._META_LINK_TTL_SEC,
            )
            return ds_id, attrs

        raise ValueError("Интеграционная привязка тега к хранилищу не найдена.")

    async def _load_operation_from_link(
            self,
            tag_id: str,
            link_cfg: dict,
            op_cn: str,
            expected_kind: OperationKind,
        ) -> OperationDef:
        cache_key = self._meta_cache_key("op", tag_id, op_cn, int(expected_kind))
        cached = await self._meta_cache_get(cache_key)
        if cached:
            if "kind" in cached:
                cached["kind"] = OperationKind(int(cached["kind"]))
            return OperationDef(**cached)

        operations = link_cfg.get("operations")
        if not isinstance(operations, list):
            raise ValueError("В конфигурации привязки не задан массив operations.")

        op_cfg = None
        for item in operations:
            if isinstance(item, dict) and item.get("cn") == op_cn:
                op_cfg = item
                break
        if op_cfg is None:
            raise ValueError(f"Операция '{op_cn}' не найдена в link.operations.")

        active = bool(op_cfg.get("prsActive", True))
        if not active:
            raise ValueError(f"Операция '{op_cn}' неактивна.")

        kind = OperationKind(int(op_cfg.get("prsEntityTypeCode", 0)))
        if kind != expected_kind:
            raise ValueError(f"Операция '{op_cn}' имеет неверный тип (prsEntityTypeCode={int(kind)}).")

        cfg = op_cfg.get("prsJsonConfigString") or {}
        query = cfg.get("query")
        if not query:
            raise ValueError(f"У операции '{op_cn}' нет ключа query.")

        validate_sql(query, kind)

        timeout_ms = cfg.get("prsTimeOutMs")
        max_rows = cfg.get("prsMaxRows")
        version = cfg.get("prsVersion")

        param_specs: dict[str, dict] = {}
        for p in op_cfg.get("parameters") or []:
            if not isinstance(p, dict):
                continue
            p_cn = p.get("cn")
            if not p_cn:
                continue
            p_active = bool(p.get("prsActive", True))
            if not p_active:
                continue
            p_cfg = p.get("prsJsonConfigString") or {}
            if not isinstance(p_cfg, dict):
                raise ValueError(f"Некорректный prsJsonConfigString у параметра '{p_cn}'.")
            param_specs[p_cn] = p_cfg

        op = OperationDef(
            id=f"{tag_id}:{op_cn}",
            cn=op_cn,
            kind=kind,
            active=active,
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
        if "y" not in cols:
            raise ValueError("Результат запроса должен содержать колонку y.")

        all_records_as_value = self._coerce_bool(req_params.get("allRecordsAsValue"), default=True)
        finish_ts = self._resolve_finish_ts(request=request)

        if all_records_as_value:
            values = [self._row_to_dict(r) for r in rows]
            return [(finish_ts, values, 0)]

        result: list[tuple] = []
        has_x = "x" in cols
        has_q = "q" in cols
        for r in rows:
            rec = self._row_to_dict(r)
            x = rec.get("x") if has_x else finish_ts
            y = rec.get("y")
            q = rec.get("q") if has_q else 0
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
        op = operation.strip().lower()
        if not op:
            return None
        if not self._RE_OP_NAME.match(op):
            raise ValueError(f"Некорректное значение params.operation: '{operation}'.")
        return op

    def _resolve_set_operation_cn(self, set_cfg: dict, requested_operation: str | None) -> str:
        operations = set_cfg.get("operations") or {}
        if not isinstance(operations, dict):
            operations = {}
        operation_cn = set_cfg.get("operationCn")
        operation_cn = self._extract_operation_cn(operation_cn)

        if requested_operation:
            op_cn = operations.get(requested_operation) or operations.get(requested_operation.upper())
            op_cn = self._extract_operation_cn(op_cn)
            if op_cn:
                return op_cn
            if operation_cn:
                return operation_cn
            raise ValueError(
                f"Не задана операция set для operation='{requested_operation}' "
                f"(ожидался set.operations.{requested_operation} или set.operationCn)."
            )

        if operation_cn:
            return operation_cn

        default_operation = self._normalize_operation_name(set_cfg.get("defaultOperation"))
        if default_operation:
            op_cn = operations.get(default_operation) or operations.get(default_operation.upper())
            op_cn = self._extract_operation_cn(op_cn)
            if op_cn:
                return op_cn

        if len(operations) == 1:
            op_cn = self._extract_operation_cn(next(iter(operations.values())))
            if op_cn:
                return op_cn

        raise ValueError("Не указан set.operationCn и не задано однозначное соответствие set.operations.")

    def _extract_operation_cn(self, value: Any) -> str | None:
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            cn = value.get("operationCn")
            if isinstance(cn, str):
                return cn
        return None

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

