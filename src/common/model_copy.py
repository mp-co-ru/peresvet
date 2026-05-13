"""
Копирование узлов модели (объекты, теги, тревоги, методы) с пересчётом
внутренних ссылок (UUID внутри копируемой подиерархии) и сохранением внешних.
"""
from __future__ import annotations

import copy
import json
import logging
import re
from typing import Any, Callable, Awaitable
from uuid import uuid4

import ldap.filter

from src.common.hierarchy import CN_SCOPE_ONELEVEL, CN_SCOPE_SUBTREE

_logger = logging.getLogger(__name__)

COPY_ENTITY_CLASSES = ("prsObject", "prsTag", "prsAlert", "prsMethod")

ENTITY_ALLOWED_ATTRS: dict[str, frozenset[str]] = {
    "prsObject": frozenset(
        {
            "cn",
            "description",
            "prsJsonConfigString",
            "prsActive",
            "prsDefault",
            "prsEntityTypeCode",
            "prsIndex",
        }
    ),
    "prsTag": frozenset(
        {
            "cn",
            "description",
            "prsJsonConfigString",
            "prsActive",
            "prsDefault",
            "prsEntityTypeCode",
            "prsIndex",
            "prsArchive",
            "prsCompress",
            "prsMaxLineDev",
            "prsStep",
            "prsUpdate",
            "prsValueTypeCode",
            "prsDefaultValue",
            "prsMeasureUnits",
        }
    ),
    "prsAlert": frozenset(
        {
            "cn",
            "description",
            "prsJsonConfigString",
            "prsActive",
            "prsDefault",
            "prsEntityTypeCode",
            "prsIndex",
        }
    ),
    "prsMethod": frozenset(
        {
            "cn",
            "description",
            "prsJsonConfigString",
            "prsActive",
            "prsDefault",
            "prsEntityTypeCode",
            "prsIndex",
            "prsMethodAddress",
        }
    ),
    "prsMethodParameter": frozenset(
        {
            "cn",
            "description",
            "prsJsonConfigString",
            "prsActive",
            "prsIndex",
        }
    ),
}

UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

LDAP_META_KEYS = frozenset(
    {
        "entryUUID",
        "creatorsName",
        "modifiersName",
        "createTimestamp",
        "modifyTimestamp",
        "structuralObjectClass",
        "subschemaSubentry",
    }
)


def first_ldap_attr_value(raw_attrs: dict[str, Any], key: str) -> str | None:
    """Первое строковое значение атрибута (LDAP-ключи сравниваются без учёта регистра)."""
    lk = key.lower()
    for k, v in raw_attrs.items():
        if str(k).lower() != lk:
            continue
        if isinstance(v, list) and v:
            x = v[0]
            if isinstance(x, str) and x.strip():
                return x
            if isinstance(x, (bytes, bytearray)):
                try:
                    s = x.decode()
                except Exception:
                    continue
                if s.strip():
                    return s
        elif isinstance(v, str) and v.strip():
            return v
    return None


def ensure_attrs_for_create(oc: str, raw_attrs: dict[str, Any], attrs_plain: dict[str, Any]) -> None:
    """Дополняет плоские атрибуты для create: cn и обязательный prsMethodAddress у методов."""
    if not str(attrs_plain.get("cn") or "").strip():
        c = first_ldap_attr_value(raw_attrs, "cn")
        if c:
            attrs_plain["cn"] = c
    if oc == "prsMethod":
        cur = attrs_plain.get("prsMethodAddress")
        if not str(cur or "").strip():
            addr = first_ldap_attr_value(raw_attrs, "prsMethodAddress")
            attrs_plain["prsMethodAddress"] = addr if addr and str(addr).strip() else " "


async def uniquify_cn_under_parent(
    hierarchy,
    parent_id: str,
    attrs_plain: dict[str, Any],
) -> None:
    """Если под родителем уже есть узел с таким cn (RDN), подбирает свободное имя."""
    base = str(attrs_plain.get("cn") or "").strip()
    if not base:
        return
    candidate = base
    n = 0
    while True:
        # Значение cn вставляется в строку фильтра без кавычек; скобки и * ломают синтаксис LDAP.
        cn_filter = ldap.filter.escape_filter_chars(candidate)
        items = await hierarchy.search(
            {
                "base": parent_id,
                "scope": CN_SCOPE_ONELEVEL,
                "filter": {"cn": [cn_filter]},
                "attributes": ["entryUUID"],
            }
        )
        if not items:
            attrs_plain["cn"] = candidate
            return
        n += 1
        if n == 1:
            candidate = f"{base} (копия)"
        else:
            candidate = f"{base} (копия {n})"
        if n > 1000:
            attrs_plain["cn"] = f"{base}-{uuid4().hex[:8]}"
            return


def filter_plain_attrs_for_class(plain: dict[str, Any], oc: str) -> dict[str, Any]:
    allowed = ENTITY_ALLOWED_ATTRS.get(oc, frozenset())
    return {k: v for k, v in plain.items() if k in allowed and v is not None}


def ldap_attrs_to_plain(attrs: dict[str, Any]) -> dict[str, Any]:
    """Преобразует ответ LDAP (значения — списки) в плоский dict для API create."""
    out: dict[str, Any] = {}
    for k, v in attrs.items():
        if k in LDAP_META_KEYS or k == "objectClass":
            continue
        if v is None:
            continue
        if isinstance(v, list):
            if not v or v[0] is None:
                continue
            if k == "prsJsonConfigString":
                raw = v[0]
                if isinstance(raw, str):
                    try:
                        out[k] = json.loads(raw) if raw.strip() else None
                    except json.JSONDecodeError:
                        out[k] = raw
                elif isinstance(raw, dict):
                    out[k] = raw
                else:
                    out[k] = raw
                continue
            out[k] = v[0] if len(v) == 1 else v
        else:
            out[k] = v
    if "prsActive" in out and isinstance(out["prsActive"], str):
        out["prsActive"] = out["prsActive"].upper() == "TRUE"
    return out


def remap_uuids_in_structure(value: Any, id_map: dict[str, str], subtree_ids: frozenset[str]) -> Any:
    """Заменяет UUID, входящие в id_map; остальные (внешние) оставляет."""

    def walk(x: Any) -> Any:
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        if isinstance(x, str):
            if x in id_map:
                return id_map[x]
            if len(x) == 36 and x in subtree_ids and x in id_map:
                return id_map[x]
            out_parts: list[str] = []
            pos = 0
            for m in UUID_RE.finditer(x):
                out_parts.append(x[pos : m.start()])
                u = m.group(0)
                out_parts.append(id_map.get(u, u))
                pos = m.end()
            out_parts.append(x[pos:])
            return "".join(out_parts) if out_parts else x
        return x

    return walk(copy.deepcopy(value))


def remap_initiated_by(initiated_by: list[str] | None, id_map: dict[str, str], subtree_ids: frozenset[str]) -> list[str]:
    if not initiated_by:
        return []
    out: list[str] = []
    for i in initiated_by:
        if i in subtree_ids and i in id_map:
            out.append(id_map[i])
        else:
            out.append(i)
    return out


async def collect_subtree_nodes(hierarchy, root_id: str) -> list[tuple[str, str, dict[str, Any]]]:
    """Все узлы поддерева с классами COPY_ENTITY_CLASSES: (id, objectClass, attrs)."""
    items = await hierarchy.search(
        {
            "base": root_id,
            "scope": CN_SCOPE_SUBTREE,
            "filter": {"objectClass": list(COPY_ENTITY_CLASSES)},
            "attributes": ["*"],
            "deref": False,
        }
    )
    return [(item[0], await hierarchy.get_node_class(item[0]), item[2]) for item in items]


async def order_nodes_tree_parents_first_async(
    hierarchy,
    root_id: str,
    nodes: list[tuple[str, str, dict[str, Any]]],
) -> list[tuple[str, str, dict[str, Any]]]:
    id_set = {n[0] for n in nodes}
    children: dict[str, list[str]] = {}
    for nid, _, _ in nodes:
        pid, _ = await hierarchy.get_parent(nid)
        if pid in id_set:
            children.setdefault(pid, []).append(nid)

    ordered: list[tuple[str, str, dict[str, Any]]] = []
    seen: set[str] = set()
    node_by_id = {n[0]: n for n in nodes}

    async def dfs(pid: str) -> None:
        for cid in children.get(pid, []):
            if cid in seen:
                continue
            seen.add(cid)
            ordered.append(node_by_id[cid])
            await dfs(cid)

    if root_id in id_set:
        seen.add(root_id)
        ordered.append(node_by_id[root_id])
        await dfs(root_id)
    return ordered


async def read_method_initiated_by_and_parameters(hierarchy, method_id: str) -> tuple[list[str], list[dict]]:
    method_dn = await hierarchy.get_node_dn(method_id)
    initiated_by: list[str] = []
    parameters: list[dict] = []

    payload_ib = {
        "base": f"cn=initiatedBy,cn=system,{method_dn}",
        "scope": CN_SCOPE_ONELEVEL,
        "filter": {"cn": ["*"]},
        "attributes": ["cn"],
    }
    for row in await hierarchy.search(payload_ib):
        initiated_by.append(row[2]["cn"][0])

    payload_p = {
        "base": f"cn=parameters,cn=system,{method_dn}",
        "scope": CN_SCOPE_ONELEVEL,
        "filter": {"objectClass": ["prsMethodParameter"]},
        "attributes": ["cn", "description", "prsActive", "prsIndex", "prsJsonConfigString"],
    }
    for row in await hierarchy.search(payload_p):
        parameters.append({"attributes": copy.deepcopy(row[2])})
    return initiated_by, parameters


async def copy_nodes_via_amqp(
    hierarchy,
    post_message: Callable[..., Awaitable[Any]],
    ordered_nodes: list[tuple[str, str, dict[str, Any]]],
    root_source_id: str,
    new_root_parent_id: str,
    id_map: dict[str, str],
    subtree_ids: frozenset[str],
    new_root_cn: str | None,
) -> dict[str, Any] | None:
    """
    Создаёт копии в порядке ordered_nodes. id_map заполняется по ходу.
    Возвращает {"id": new_root_id} или {"error": ...}.
    """
    routing = {
        "prsObject": "prsObject.api_crud.create",
        "prsTag": "prsTag.api_crud.create",
        "prsAlert": "prsAlert.api_crud.create",
        "prsMethod": "prsMethod.api_crud.create",
    }

    for nid, oc, raw_attrs in ordered_nodes:
        attrs_plain = filter_plain_attrs_for_class(ldap_attrs_to_plain(raw_attrs), oc)
        ensure_attrs_for_create(oc, raw_attrs, attrs_plain)
        if nid == root_source_id and new_root_cn:
            attrs_plain["cn"] = new_root_cn

        if oc == "prsMethod":
            ib, params = await read_method_initiated_by_and_parameters(hierarchy, nid)
            ib2 = remap_initiated_by(ib, id_map, subtree_ids)
            params2 = []
            for p in params:
                raw_p = p.get("attributes", {})
                a = filter_plain_attrs_for_class(
                    ldap_attrs_to_plain(raw_p), "prsMethodParameter"
                )
                ensure_attrs_for_create("prsMethodParameter", raw_p, a)
                if "prsJsonConfigString" in a and a["prsJsonConfigString"] is not None:
                    a["prsJsonConfigString"] = remap_uuids_in_structure(
                        a["prsJsonConfigString"], id_map, subtree_ids
                    )
                params2.append({"attributes": a})
            parent_old, _ = await hierarchy.get_parent(nid)
            if nid == root_source_id:
                new_parent = new_root_parent_id
            elif parent_old in id_map:
                new_parent = id_map[parent_old]
            else:
                return {
                    "error": {
                        "code": 422,
                        "message": (
                            f"Копирование: родитель {parent_old} узла {nid} не в id_map "
                            f"(ожидался только корень вне поддерева)."
                        ),
                    }
                }
            await uniquify_cn_under_parent(hierarchy, new_parent, attrs_plain)
            body = {
                "parentId": new_parent,
                "attributes": attrs_plain,
                "initiatedBy": ib2,
                "parameters": params2 if params2 else None,
            }
        else:
            parent_old, _ = await hierarchy.get_parent(nid)
            if nid == root_source_id:
                new_parent = new_root_parent_id
            elif parent_old in id_map:
                new_parent = id_map[parent_old]
            else:
                return {
                    "error": {
                        "code": 422,
                        "message": (
                            f"Копирование: родитель {parent_old} узла {nid} не в id_map."
                        ),
                    }
                }
            await uniquify_cn_under_parent(hierarchy, new_parent, attrs_plain)
            if "prsJsonConfigString" in attrs_plain and attrs_plain["prsJsonConfigString"] is not None:
                attrs_plain["prsJsonConfigString"] = remap_uuids_in_structure(
                    attrs_plain["prsJsonConfigString"], id_map, subtree_ids
                )
            body = {"parentId": new_parent, "attributes": attrs_plain}

        res = await post_message(mes=body, reply=True, routing_key=routing[oc])
        if not res or res.get("id") is None:
            return {
                "error": {
                    "code": 422,
                    "message": f"Ошибка копирования узла {nid} ({oc}): {res}",
                }
            }
        new_id = res["id"]
        id_map[nid] = new_id

    return {"id": id_map.get(root_source_id)}


def _safe_json_ldap(val: Any, default: Any) -> Any:
    if val is None:
        return default
    raw = val[0] if isinstance(val, list) and val else val
    if raw is None:
        return default
    if isinstance(raw, (dict, list, int, float, bool)):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return default
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return raw
    return raw


def _ldap_row_to_flat_payload(attrs: dict[str, Any]) -> dict[str, Any]:
    """Плоский dict атрибутов LDAP-узла для тел операций привязки (как в v2 model)."""
    result: dict[str, Any] = {}
    for key, raw in attrs.items():
        if key in ("entryUUID", "entryuuid", "prsIndex"):
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
            value = _safe_json_ldap(raw, default={})
        result[key] = value
    return result


async def _read_tag_link_operations_under_link(
    hierarchy, link_id: str
) -> list[dict[str, Any]]:
    ops = await hierarchy.search(
        {
            "base": link_id,
            "scope": CN_SCOPE_ONELEVEL,
            "filter": {"objectClass": ["prsDatastorageTagOperation"]},
            "attributes": ["*"],
            "deref": False,
        }
    )
    if not ops:
        return []
    result: list[dict[str, Any]] = []
    for op_id, _, attrs in ops:
        params = await hierarchy.search(
            {
                "base": op_id,
                "scope": CN_SCOPE_ONELEVEL,
                "filter": {"objectClass": ["prsDatastorageTagOperationParameter"]},
                "attributes": ["*"],
                "deref": False,
            }
        )
        param_items: list[dict[str, Any]] = []
        for _, __, p_attrs in params or []:
            param_items.append({"attributes": _ldap_row_to_flat_payload(p_attrs)})
        result.append(
            {
                "attributes": _ldap_row_to_flat_payload(attrs),
                "parameters": param_items,
            }
        )
    return result


def _remap_link_operations(
    operations: list[dict[str, Any]],
    id_map: dict[str, str],
    subtree_ids: frozenset[str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for op in operations:
        op2 = copy.deepcopy(op)
        attrs = op2.get("attributes") or {}
        cfg = attrs.get("prsJsonConfigString")
        if isinstance(cfg, (dict, list)):
            attrs["prsJsonConfigString"] = remap_uuids_in_structure(cfg, id_map, subtree_ids)
        for p in op2.get("parameters") or []:
            pa = p.get("attributes") or {}
            pc = pa.get("prsJsonConfigString")
            if isinstance(pc, (dict, list)):
                pa["prsJsonConfigString"] = remap_uuids_in_structure(pc, id_map, subtree_ids)
        out.append(op2)
    return out


async def _list_data_storage_node_ids(hierarchy) -> list[str]:
    ds_root = await hierarchy.get_node_id("cn=dataStorages,cn=prs")
    if not ds_root:
        return []
    rows = await hierarchy.search(
        {
            "base": ds_root,
            "scope": CN_SCOPE_ONELEVEL,
            "filter": {"objectClass": ["prsDataStorage"]},
            "attributes": ["cn"],
            "deref": False,
        }
    )
    return [row[0] for row in rows or []]


async def replicate_storage_links_for_subtree_copy(
    hierarchy,
    post_message: Callable[..., Awaitable[Any]],
    *,
    id_map: dict[str, str],
    subtree_ids: frozenset[str],
    subtree_nodes: list[tuple[str, str, dict[str, Any]]],
) -> None:
    """Восстанавливает привязки тегов/тревог к тем же хранилищам после копирования поддерева."""
    old_tag_ids = frozenset(nid for nid, oc, _ in subtree_nodes if oc == "prsTag")
    old_alert_ids = frozenset(nid for nid, oc, _ in subtree_nodes if oc == "prsAlert")
    if not old_tag_ids and not old_alert_ids:
        return
    ds_ids = await _list_data_storage_node_ids(hierarchy)
    if not ds_ids:
        return

    for ds_id in ds_ids:
        linked_tags: list[dict[str, Any]] = []
        linked_alerts: list[dict[str, Any]] = []
        try:
            tag_rows = await hierarchy.search(
                {
                    "base": ds_id,
                    "scope": CN_SCOPE_SUBTREE,
                    "filter": {"objectClass": ["prsDatastorageTagData"]},
                    # prsStore не передаём при привязке: приложение хранилища само
                    # создаёт таблицу; из LDAP prsStore часто строка JSON — ломает .get() в app.
                    "attributes": ["cn", "prsJsonConfigString", "prsEntityTypeCode"],
                    "deref": False,
                }
            )
            for link_id, _, raw in tag_rows or []:
                old_tid = first_ldap_attr_value(raw, "cn")
                if not old_tid or old_tid not in old_tag_ids or old_tid not in id_map:
                    continue
                new_tid = id_map[old_tid]
                plain = ldap_attrs_to_plain(raw)
                attrs_out: dict[str, Any] = {"cn": new_tid}
                for k in ("prsJsonConfigString", "prsEntityTypeCode"):
                    if k not in plain or plain[k] is None:
                        continue
                    val = plain[k]
                    if k == "prsJsonConfigString":
                        val = remap_uuids_in_structure(val, id_map, subtree_ids)
                    attrs_out[k] = val
                entry: dict[str, Any] = {"tagId": new_tid, "attributes": attrs_out}
                ops = await _read_tag_link_operations_under_link(hierarchy, link_id)
                if ops:
                    entry["operations"] = _remap_link_operations(ops, id_map, subtree_ids)
                linked_tags.append(entry)

            alert_rows = await hierarchy.search(
                {
                    "base": ds_id,
                    "scope": CN_SCOPE_SUBTREE,
                    "filter": {"objectClass": ["prsDatastorageAlertData"]},
                    "attributes": ["cn"],
                    "deref": False,
                }
            )
            for _, _, raw in alert_rows or []:
                old_aid = first_ldap_attr_value(raw, "cn")
                if not old_aid or old_aid not in old_alert_ids or old_aid not in id_map:
                    continue
                new_aid = id_map[old_aid]
                linked_alerts.append({"alertId": new_aid, "attributes": {"cn": new_aid}})
        except Exception as ex:
            _logger.warning(
                "Копирование: не удалось собрать привязки для хранилища %s: %s",
                ds_id,
                ex,
            )
            continue

        if not linked_tags and not linked_alerts:
            continue
        try:
            res = await post_message(
                mes={
                    "id": ds_id,
                    "linkedTags": linked_tags,
                    "linkedAlerts": linked_alerts,
                },
                reply=True,
                routing_key=f"prsDataStorage.api_crud.update.{ds_id}",
            )
            if isinstance(res, dict) and res.get("error"):
                _logger.warning(
                    "Копирование: привязки к хранилищу %s не применены: %s",
                    ds_id,
                    res.get("error"),
                )
        except Exception as ex:
            _logger.warning(
                "Копирование: ошибка AMQP при восстановлении привязок для хранилища %s: %s",
                ds_id,
                ex,
            )


async def copy_subtree_rooted_at(
    hierarchy,
    post_message: Callable[..., Awaitable[Any]],
    *,
    root_source_id: str,
    expected_root_class: str,
    new_parent_id: str,
    new_root_cn: str | None = None,
) -> dict[str, Any]:
    oc = await hierarchy.get_node_class(root_source_id)
    if oc != expected_root_class:
        return {
            "error": {
                "code": 422,
                "message": f"Ожидался узел класса {expected_root_class}, получен {oc}.",
            }
        }

    nodes = await collect_subtree_nodes(hierarchy, root_source_id)
    subtree_ids = frozenset(n[0] for n in nodes)
    non_method = [n for n in nodes if n[1] != "prsMethod"]
    methods = [n for n in nodes if n[1] == "prsMethod"]

    ordered_non_method = await order_nodes_tree_parents_first_async(hierarchy, root_source_id, non_method)

    id_map: dict[str, str] = {}

    r1 = await copy_nodes_via_amqp(
        hierarchy,
        post_message,
        ordered_non_method,
        root_source_id,
        new_parent_id,
        id_map,
        subtree_ids,
        new_root_cn,
    )
    if r1 and r1.get("error"):
        return r1

    unresolved = list(methods)
    max_passes = len(methods) + 2
    for _ in range(max_passes):
        if not unresolved:
            break
        progress: list[tuple[str, str, dict[str, Any]]] = []
        still: list[tuple[str, str, dict[str, Any]]] = []
        for m in unresolved:
            mid, moc, mattrs = m
            ib, _ = await read_method_initiated_by_and_parameters(hierarchy, mid)
            ok = True
            for i in ib:
                if i in subtree_ids and i not in id_map:
                    ok = False
                    break
            if ok:
                pj = filter_plain_attrs_for_class(ldap_attrs_to_plain(mattrs), "prsMethod")
                ensure_attrs_for_create("prsMethod", mattrs, pj)
                if pj.get("prsJsonConfigString") is not None:
                    if pending_internal_refs(pj["prsJsonConfigString"], subtree_ids, id_map):
                        ok = False
            if ok:
                progress.append(m)
            else:
                still.append(m)
        if not progress:
            return {
                "error": {
                    "code": 422,
                    "message": "Не удалось разрешить зависимости методов при копировании (циклические ссылки?).",
                }
            }
        r2 = await copy_nodes_via_amqp(
            hierarchy,
            post_message,
            progress,
            root_source_id,
            new_parent_id,
            id_map,
            subtree_ids,
            None,
        )
        if r2 and r2.get("error"):
            return r2
        unresolved = still

    if unresolved:
        return {"error": {"code": 422, "message": "Остались нескопированные методы."}}

    new_root = id_map.get(root_source_id)
    if not new_root:
        return {"error": {"code": 422, "message": "Не определён id корня копии."}}
    await replicate_storage_links_for_subtree_copy(
        hierarchy,
        post_message,
        id_map=id_map,
        subtree_ids=subtree_ids,
        subtree_nodes=nodes,
    )
    return {"id": new_root}


def pending_internal_refs(obj: Any, subtree_ids: frozenset[str], id_map: dict[str, str]) -> bool:
    """True, если в структуре есть UUID из subtree_ids, ещё не попавший в id_map."""

    def walk(x: Any) -> bool:
        if isinstance(x, dict):
            return any(walk(v) for v in x.values())
        if isinstance(x, list):
            return any(walk(v) for v in x)
        if isinstance(x, str):
            if x in subtree_ids and x not in id_map:
                return True
            for m in UUID_RE.finditer(x):
                u = m.group(0)
                if u in subtree_ids and u not in id_map:
                    return True
        return False

    return walk(obj)


async def copy_single_method(
    hierarchy,
    post_message: Callable[..., Awaitable[Any]],
    *,
    source_id: str,
    new_parent_id: str,
    subtree_ids: frozenset[str],
    id_map: dict[str, str],
) -> dict[str, Any]:
    oc = await hierarchy.get_node_class(source_id)
    if oc != "prsMethod":
        return {"error": {"code": 422, "message": "Источник должен быть методом."}}
    raw_items = await hierarchy.search(
        {"id": [source_id], "attributes": ["*"], "deref": False}
    )
    if not raw_items:
        return {"error": {"code": 422, "message": "Метод не найден."}}
    _, _, raw_attrs = raw_items[0]
    ib, params = await read_method_initiated_by_and_parameters(hierarchy, source_id)
    ib2 = remap_initiated_by(ib, id_map, subtree_ids)
    params2 = []
    for p in params:
        raw_p = p.get("attributes", {})
        a = filter_plain_attrs_for_class(
            ldap_attrs_to_plain(raw_p), "prsMethodParameter"
        )
        ensure_attrs_for_create("prsMethodParameter", raw_p, a)
        if "prsJsonConfigString" in a and a["prsJsonConfigString"] is not None:
            a["prsJsonConfigString"] = remap_uuids_in_structure(a["prsJsonConfigString"], id_map, subtree_ids)
        params2.append({"attributes": a})
    attrs_plain = ldap_attrs_to_plain(raw_attrs)
    ensure_attrs_for_create("prsMethod", raw_attrs, attrs_plain)
    body = {
        "parentId": new_parent_id,
        "attributes": attrs_plain,
        "initiatedBy": ib2,
        "parameters": params2 or None,
    }
    res = await post_message(mes=body, reply=True, routing_key="prsMethod.api_crud.create")
    if not res or res.get("id") is None:
        return {"error": {"code": 422, "message": f"Ошибка копирования метода: {res}"}}
    return {"id": res["id"]}
